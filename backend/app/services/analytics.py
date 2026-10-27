from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.config import timezone_name
from backend.app.models import Trade


def filtered_statement(*, from_: str | None, to: str | None, instrument: str | None,
                       market: str | None, strategy: str | None, closed: bool):
    statement = select(Trade)
    if instrument:
        statement = statement.where(Trade.instrument == instrument)
    if market:
        statement = statement.where(Trade.market == market)
    if strategy:
        statement = statement.where(Trade.strategy == strategy)
    date_column = Trade.closed_at if closed else Trade.opened_at
    if from_:
        statement = statement.where(date_column >= from_)
    if to:
        statement = statement.where(date_column <= to)
    return statement.where(Trade.closed_at.is_not(None) if closed else Trade.closed_at.is_(None))


def _net(row: Trade) -> Decimal:
    if row.closed_at is None or row.exit_price is None:
        return Decimal(0)
    if row.realized_pnl_override is not None:
        return row.realized_pnl_override - row.fees
    direction = Decimal("1") if row.direction == "long" else Decimal("-1")
    return (row.exit_price - row.entry_price) * direction * row.size * row.multiplier - row.fees


def _decimal_text(value: Decimal) -> str:
    text = format(value, "f")
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return text or "0"


def build_summary(session: Session, from_: str | None = None, to: str | None = None,
                  instrument: str | None = None, market: str | None = None,
                  strategy: str | None = None) -> dict[str, Any]:
    closed_statement = filtered_statement(from_=from_, to=to, instrument=instrument,
                                          market=market, strategy=strategy, closed=True)
    groups: dict[str, list[tuple[Trade, Decimal]]] = defaultdict(list)
    for row in session.scalars(closed_statement).all():
        groups[row.currency].append((row, _net(row)))

    currencies = []
    equity = []
    for code in sorted(groups):
        positions = groups[code]
        values = [pnl for _, pnl in positions]
        wins = [value for value in values if value > 0]
        losses = [value for value in values if value < 0]
        positive_total = sum(wins, Decimal(0))
        negative_total = sum(losses, Decimal(0))
        currencies.append({
            "currency": code,
            "closed_count": len(values),
            "wins": len(wins),
            "losses": len(losses),
            "breakeven": sum(value == 0 for value in values),
            "win_rate": _decimal_text(Decimal(len(wins)) / Decimal(len(values))) if values else None,
            "net_pnl": _decimal_text(sum(values, Decimal(0))),
            "average_win": _decimal_text(positive_total / len(wins)) if wins else None,
            "average_loss": _decimal_text(negative_total / len(losses)) if losses else None,
            "profit_factor": _decimal_text(positive_total / abs(negative_total)) if losses else None,
        })
        running = Decimal(0)
        for row, pnl in sorted(positions, key=lambda item: (item[0].closed_at or "", item[0].id)):
            running += pnl
            equity.append({"currency": code, "at": row.closed_at, "net_pnl": _decimal_text(pnl),
                           "cumulative_pnl": _decimal_text(running)})

    open_statement = filtered_statement(from_=from_, to=to, instrument=instrument,
                                        market=market, strategy=strategy, closed=False)
    open_count = len(session.scalars(open_statement).all())
    return {"currencies": currencies, "equity": equity, "open_count": open_count}


def build_calendar(session: Session, year: int, month: int, currency: str | None = None,
                   instrument: str | None = None, market: str | None = None,
                   strategy: str | None = None) -> dict[str, Any]:
    if year < 1 or year > 9999 or month < 1 or month > 12:
        raise ValueError("Year and month are outside supported bounds.")
    local_start = date(year, month, 1)
    if year == 9999 and month == 12:
        local_end = date.max
        start_utc = datetime(year, month, 1, tzinfo=timezone.utc) - timedelta(days=2)
        end_utc = datetime.max.replace(tzinfo=timezone.utc)
    else:
        local_end = date(year + (month == 12), month % 12 + 1, 1)
        start_utc = datetime.combine(local_start, datetime.min.time(), timezone.utc) - timedelta(days=2)
        end_utc = datetime.combine(local_end, datetime.min.time(), timezone.utc) + timedelta(days=2)

    statement = select(Trade).where(
        Trade.closed_at.is_not(None),
        Trade.closed_at >= start_utc.isoformat(timespec="seconds").replace("+00:00", "Z"),
        Trade.closed_at < end_utc.isoformat(timespec="seconds").replace("+00:00", "Z"),
    )
    for column, value in ((Trade.currency, currency), (Trade.instrument, instrument),
                          (Trade.market, market), (Trade.strategy, strategy)):
        if value:
            statement = statement.where(column == value)

    local_zone = ZoneInfo(timezone_name())
    grouped: dict[tuple[str, str], tuple[int, Decimal]] = defaultdict(lambda: (0, Decimal(0)))
    for row in session.scalars(statement).all():
        closed_at = datetime.fromisoformat(row.closed_at.replace("Z", "+00:00"))
        local_date = closed_at.astimezone(local_zone).date()
        if not local_start <= local_date < local_end:
            continue
        key = (local_date.isoformat(), row.currency)
        count, total = grouped[key]
        grouped[key] = (count + 1, total + _net(row))

    days = [{"date": day, "currency": code, "closed_count": count, "net_pnl": _decimal_text(total)}
            for (day, code), (count, total) in sorted(grouped.items())]
    return {"year": year, "month": month, "days": days}
