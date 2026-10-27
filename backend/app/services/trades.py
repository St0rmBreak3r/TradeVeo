from decimal import Decimal

from typing import Protocol


class Position(Protocol):
    closed_at: object | None
    exit_price: Decimal | None
    realized_pnl_override: Decimal | None
    direction: str
    entry_price: Decimal
    size: Decimal
    multiplier: Decimal
    fees: Decimal


def calculate_gross_pnl(trade: Position) -> Decimal | None:
    if trade.closed_at is None or trade.exit_price is None:
        return None
    if trade.realized_pnl_override is not None:
        return trade.realized_pnl_override
    direction_sign = Decimal("1") if trade.direction == "long" else Decimal("-1")
    return (trade.exit_price - trade.entry_price) * direction_sign * trade.size * trade.multiplier


def calculate_net_pnl(trade: Position) -> Decimal | None:
    gross = calculate_gross_pnl(trade)
    return None if gross is None else gross - trade.fees
