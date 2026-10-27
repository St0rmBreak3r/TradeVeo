from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from backend.app.api.dependencies import db_session
from backend.app.services.analytics import build_calendar, build_summary

router = APIRouter(prefix="/api", tags=["analytics"])


@router.get("/analytics/summary")
def analytics_summary(
    session: Session = Depends(db_session),
    from_: str | None = Query(default=None, alias="from"),
    to: str | None = None,
    instrument: str | None = None,
    market: str | None = None,
    strategy: str | None = None,
):
    return build_summary(session, from_, to, instrument, market, strategy)


@router.get("/calendar")
def calendar(
    year: int = Query(ge=1, le=9999),
    month: int = Query(ge=1, le=12),
    currency: str | None = None,
    instrument: str | None = None,
    market: str | None = None,
    strategy: str | None = None,
    session: Session = Depends(db_session),
):
    try:
        return build_calendar(session, year, month, currency, instrument, market, strategy)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
