from __future__ import annotations

import csv
import io
import json
import os
import re
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Generator

from fastapi import Depends, FastAPI, File, HTTPException, Query, Request, Response, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from backend.app.config import backup_directory, database_url as configured_database_url, ui_origin
from backend.app.database import initialize_schema, make_engine, make_session_factory
from backend.app.api.analytics import router as analytics_router
from backend.app.api.chart_analysis import router as chart_analysis_router
from backend.app.services.chart_providers import create_chart_provider
from backend.app.services.ai_settings import load_provider_config
from backend.app.services.credentials import resolve_api_key
from backend.app.models import Trade
from backend.app.services.trades import calculate_gross_pnl, calculate_net_pnl
from backend.app.services.csv_io import CSV_COLUMNS, MAX_FILE_BYTES, export_trades, parse_csv
from backend.app.services.backups import create_backup, list_backups, restore_backup

_ALLOWED_MARKETS = {"equities", "forex", "futures", "options", "crypto", "other"}
_ALLOWED_SORTS = {"opened_at", "closed_at", "instrument", "currency", "direction", "net_pnl"}
_ALLOWED_STATUSES = {"open", "closed"}
_DECIMAL_PATTERN = re.compile(r"^-?(?:0|[1-9]\d*)(?:\.\d+)?$")


def _decimal(value: Any) -> Decimal:
    if isinstance(value, Decimal):
        result = value
    elif isinstance(value, str) and _DECIMAL_PATTERN.fullmatch(value):
        try:
            result = Decimal(value)
        except InvalidOperation as exc:
            raise ValueError("Enter a valid decimal number.") from exc
    else:
        raise ValueError("Decimal values must be plain decimal strings.")
    if not result.is_finite():
        raise ValueError("Decimal values must be finite.")
    return result


def _decimal_text(value: Decimal | None) -> str | None:
    if value is None:
        return None
    text = format(value, "f")
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return text or "0"


def _iso_utc(value: datetime | None) -> str | None:
    if value is None:
        return None
    return value.astimezone(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


class TradeCreate(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    instrument: str = Field(min_length=1, max_length=40)
    market: str | None = None
    direction: str
    opened_at: datetime
    closed_at: datetime | None = None
    entry_price: Decimal
    exit_price: Decimal | None = None
    size: Decimal
    multiplier: Decimal = Decimal("1")
    fees: Decimal = Decimal("0")
    currency: str = Field(pattern=r"^[A-Z]{3}$")
    realized_pnl_override: Decimal | None = None
    strategy: str | None = Field(default=None, max_length=120)
    tags: list[str] = Field(default_factory=list, max_length=20)
    notes: str | None = Field(default=None, max_length=4000)

    @field_validator("entry_price", "exit_price", "size", "multiplier", "fees", "realized_pnl_override", mode="before")
    @classmethod
    def strict_decimal_strings(cls, value: Any) -> Any:
        return None if value is None else _decimal(value)

    @field_validator("direction")
    @classmethod
    def valid_direction(cls, value: str) -> str:
        if value not in {"long", "short"}:
            raise ValueError("Direction must be long or short.")
        return value

    @field_validator("market")
    @classmethod
    def valid_market(cls, value: str | None) -> str | None:
        if value is not None and value not in _ALLOWED_MARKETS:
            raise ValueError("Choose a supported market.")
        return value

    @field_validator("opened_at", "closed_at")
    @classmethod
    def require_timezone(cls, value: datetime | None) -> datetime | None:
        if value is not None and value.utcoffset() is None:
            raise ValueError("Timestamps must include a timezone.")
        return value

    @field_validator("entry_price", "size", "multiplier")
    @classmethod
    def require_positive(cls, value: Decimal) -> Decimal:
        if value <= 0:
            raise ValueError("Value must be greater than zero.")
        return value

    @field_validator("exit_price")
    @classmethod
    def require_positive_exit(cls, value: Decimal | None) -> Decimal | None:
        if value is not None and value <= 0:
            raise ValueError("Exit price must be greater than zero.")
        return value

    @field_validator("fees")
    @classmethod
    def require_nonnegative_fees(cls, value: Decimal) -> Decimal:
        if value < 0:
            raise ValueError("Fees cannot be negative.")
        return value

    @field_validator("tags")
    @classmethod
    def validate_tags(cls, tags: list[str]) -> list[str]:
        cleaned = [tag.strip() for tag in tags]
        if any(not tag or len(tag) > 40 for tag in cleaned):
            raise ValueError("Tags must contain 1 to 40 characters.")
        if len(set(cleaned)) != len(cleaned):
            raise ValueError("Tags must be unique.")
        return cleaned

    @model_validator(mode="after")
    def validate_close(self) -> "TradeCreate":
        if (self.closed_at is None) != (self.exit_price is None):
            raise ValueError("Closed time and exit price must both be set or both be empty.")
        if self.closed_at is not None and self.closed_at < self.opened_at:
            raise ValueError("Closed time cannot be earlier than opened time.")
        if self.realized_pnl_override is not None and self.closed_at is None:
            raise ValueError("A realized P&L override requires a closed position.")
        return self


def _trade_values(payload: TradeCreate) -> dict[str, Any]:
    return {
        "instrument": payload.instrument,
        "market": payload.market,
        "direction": payload.direction,
        "opened_at": _iso_utc(payload.opened_at),
        "closed_at": _iso_utc(payload.closed_at),
        "entry_price": payload.entry_price,
        "exit_price": payload.exit_price,
        "size": payload.size,
        "multiplier": payload.multiplier,
        "fees": payload.fees,
        "currency": payload.currency,
        "realized_pnl_override": payload.realized_pnl_override,
        "strategy": payload.strategy,
        "tags": "\x1f".join(payload.tags),
        "notes": payload.notes,
    }


def _trade_read(row: Trade) -> dict[str, Any]:
    data = {
        "instrument": row.instrument,
        "market": row.market,
        "direction": row.direction,
        "opened_at": datetime.fromisoformat(row.opened_at.replace("Z", "+00:00")),
        "closed_at": None if row.closed_at is None else datetime.fromisoformat(row.closed_at.replace("Z", "+00:00")),
        "entry_price": row.entry_price,
        "exit_price": row.exit_price,
        "size": row.size,
        "multiplier": row.multiplier,
        "fees": row.fees,
        "currency": row.currency,
        "realized_pnl_override": row.realized_pnl_override,
        "strategy": row.strategy,
        "tags": row.tags.split("\x1f") if row.tags else [],
        "notes": row.notes,
    }
    payload = TradeCreate.model_validate(data)
    return {
        "id": row.id,
        **{key: (_decimal_text(value) if isinstance(value, Decimal) else value) for key, value in data.items() if key != "tags"},
        "tags": data["tags"],
        "opened_at": _iso_utc(payload.opened_at),
        "closed_at": _iso_utc(payload.closed_at),
        "gross_pnl": _decimal_text(calculate_gross_pnl(payload)),
        "net_pnl": _decimal_text(calculate_net_pnl(payload)),
        "created_at": row.created_at,
        "updated_at": row.updated_at,
    }


def _filtered_statement(*, search: str | None, instrument: str | None, market: str | None,
                        direction: str | None, strategy: str | None, from_: str | None,
                        to: str | None, status: str | None, currency: str | None):
    statement = select(Trade)
    if search:
        pattern = f"%{search}%"
        statement = statement.where(
            Trade.instrument.ilike(pattern) | Trade.strategy.ilike(pattern) | Trade.notes.ilike(pattern)
        )
    for column, value in ((Trade.instrument, instrument), (Trade.market, market),
                          (Trade.direction, direction), (Trade.strategy, strategy),
                          (Trade.currency, currency)):
        if value:
            statement = statement.where(column == value)
    if from_:
        statement = statement.where(Trade.opened_at >= from_)
    if to:
        statement = statement.where(Trade.opened_at <= to)
    if status == "open":
        statement = statement.where(Trade.closed_at.is_(None))
    elif status == "closed":
        statement = statement.where(Trade.closed_at.is_not(None))
    return statement


def create_app(database_url: str | None = None) -> FastAPI:
    url = database_url or configured_database_url()
    configured_origin = ui_origin()
    local_origins = {configured_origin, "http://127.0.0.1:8010", "http://localhost:8010"}

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        engine = make_engine(url)
        initialize_schema(engine)
        app.state.engine = engine
        app.state.session_factory = make_session_factory(engine)
        app.state.import_previews = {}
        yield
        engine.dispose()

    app = FastAPI(title="TradeVeo", version="0.1.0", lifespan=lifespan)
    app.state.database_url = url
    app.state.allowed_origin = configured_origin
    app.state.local_origins = local_origins
    app.state.chart_provider_factory = lambda api_key: create_chart_provider(load_provider_config(), api_key)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=sorted(local_origins),
        allow_credentials=False,
        allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
        allow_headers=["Content-Type"],
    )

    @app.middleware("http")
    async def local_request_guard(request: Request, call_next):
        host = request.headers.get("host", "").split(":", 1)[0].strip("[]").lower()
        if host not in {"localhost", "127.0.0.1", "testserver"}:
            return Response(status_code=400, content="Local host only")
        if request.method not in {"GET", "HEAD", "OPTIONS"}:
            origin = request.headers.get("origin")
            fetch_site = request.headers.get("sec-fetch-site")
            if origin not in request.app.state.local_origins or fetch_site == "cross-site":
                return Response(status_code=403, content="Same-origin request required")
        return await call_next(request)

    def db(request: Request) -> Generator[Session, None, None]:
        with request.app.state.session_factory() as session:
            yield session

    @app.get("/api/health")
    def health(request: Request):
        return {"status": "ok", "schema_version": "0001" if hasattr(request.app.state, "session_factory") else "0000"}

    @app.post("/api/trades", status_code=201)
    def create_trade(payload: TradeCreate, session: Session = Depends(db)):
        now = datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
        row = Trade(id=str(uuid.uuid4()), created_at=now, updated_at=now, **_trade_values(payload))
        session.add(row)
        session.commit()
        session.refresh(row)
        return _trade_read(row)

    @app.get("/api/trades")
    def list_trades(
        session: Session = Depends(db),
        search: str | None = None,
        instrument: str | None = None,
        market: str | None = None,
        direction: str | None = None,
        strategy: str | None = None,
        from_: str | None = Query(default=None, alias="from"),
        to: str | None = None,
        status: str | None = None,
        currency: str | None = None,
        sort: str = "opened_at",
        order: str = "desc",
        limit: int = Query(default=50, ge=1, le=200),
        offset: int = Query(default=0, ge=0),
    ):
        if sort not in _ALLOWED_SORTS or order not in {"asc", "desc"} or (status is not None and status not in _ALLOWED_STATUSES):
            raise HTTPException(status_code=422, detail="Invalid list filter or sort option.")
        base = _filtered_statement(search=search, instrument=instrument, market=market,
                                   direction=direction, strategy=strategy, from_=from_,
                                   to=to, status=status, currency=currency)
        total = session.scalar(select(func.count()).select_from(base.order_by(None).subquery())) or 0
        sort_column = getattr(Trade, sort)
        ordered = base.order_by(sort_column.asc() if order == "asc" else sort_column.desc(), Trade.id.asc())
        rows = session.scalars(ordered.offset(offset).limit(limit)).all()
        return {"items": [_trade_read(row) for row in rows], "total": total, "limit": limit, "offset": offset}

    @app.get("/api/trades/{trade_id}")
    def get_trade(trade_id: str, session: Session = Depends(db)):
        row = session.get(Trade, trade_id)
        if row is None:
            raise HTTPException(status_code=404, detail="Trade not found.")
        return _trade_read(row)

    @app.put("/api/trades/{trade_id}")
    def update_trade(trade_id: str, payload: TradeCreate, session: Session = Depends(db)):
        row = session.get(Trade, trade_id)
        if row is None:
            raise HTTPException(status_code=404, detail="Trade not found.")
        for key, value in _trade_values(payload).items():
            setattr(row, key, value)
        row.updated_at = datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
        session.commit()
        session.refresh(row)
        return _trade_read(row)

    @app.delete("/api/trades/{trade_id}", status_code=204)
    def delete_trade(trade_id: str, session: Session = Depends(db)):
        row = session.get(Trade, trade_id)
        if row is None:
            raise HTTPException(status_code=404, detail="Trade not found.")
        session.delete(row)
        session.commit()
        return Response(status_code=204)

    app.include_router(analytics_router)
    app.include_router(chart_analysis_router)

    @app.get("/api/export.csv")
    def export_csv(
        session: Session = Depends(db), search: str | None = None, instrument: str | None = None,
        market: str | None = None, direction: str | None = None, strategy: str | None = None,
        from_: str | None = Query(default=None, alias="from"), to: str | None = None,
        status: str | None = None, currency: str | None = None,
    ):
        rows = session.scalars(_filtered_statement(search=search, instrument=instrument, market=market,
            direction=direction, strategy=strategy, from_=from_, to=to, status=status, currency=currency)).all()
        content = export_trades([_trade_read(row) for row in rows])
        return Response(content=content, media_type="text/csv; charset=utf-8", headers={"Content-Disposition": "attachment; filename=tryedveo-trades.csv"})

    @app.post("/api/import/preview")
    async def import_preview(request: Request, file: UploadFile = File(...)):
        contents = await file.read(MAX_FILE_BYTES + 1)
        if len(contents) > MAX_FILE_BYTES:
            raise HTTPException(status_code=413, detail="CSV file must be no larger than 10 MiB.")
        try:
            parsed = parse_csv(contents)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        previews = request.app.state.import_previews
        if len(previews) >= 10:
            previews.pop(next(iter(previews)))
        preview_token = str(uuid.uuid4())
        request.app.state.import_previews[preview_token] = parsed
        return {"preview_token": preview_token, "headers": parsed["headers"], "row_count": parsed["row_count"],
                "valid_count": len(parsed["valid_rows"]), "errors": parsed["errors"]}

    @app.post("/api/import/commit")
    def import_commit(payload: dict[str, Any], request: Request, session: Session = Depends(db)):
        if payload.get("confirm_valid_rows") is not True:
            raise HTTPException(status_code=400, detail="Confirm the valid rows before importing.")
        token = payload.get("preview_token")
        preview = request.app.state.import_previews.pop(token, None) if isinstance(token, str) else None
        if preview is None:
            raise HTTPException(status_code=422, detail="Import preview expired or not found; preview the CSV again.")
        rows = []
        for item in preview["valid_rows"]:
            trade = TradeCreate.model_validate(item)
            now = datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
            rows.append(Trade(id=str(uuid.uuid4()), created_at=now, updated_at=now, **_trade_values(trade)))
        try:
            session.add_all(rows)
            session.commit()
        except Exception:
            session.rollback()
            raise
        return {"created": len(rows), "skipped_invalid": len(preview["errors"])}

    @app.post("/api/backups")
    def make_backup(request: Request):
        try:
            return create_backup(url, request.app.state.engine)
        except ValueError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc

    @app.get("/api/backups")
    def backups_list():
        return list_backups()

    @app.post("/api/backups/restore")
    def backup_restore(payload: dict[str, Any], request: Request):
        try:
            return restore_backup(payload.get("backup_id", ""), payload.get("confirm") is True, url,
                                  request.app.state.engine, request.app.state.session_factory)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    frontend_dist = Path(__file__).resolve().parents[2] / "dist"
    if frontend_dist.is_dir():
        app.mount("/", StaticFiles(directory=frontend_dist, html=True), name="frontend")

    return app


app = create_app()
