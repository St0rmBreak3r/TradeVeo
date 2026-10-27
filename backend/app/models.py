from __future__ import annotations

from decimal import Decimal
from typing import Any

from sqlalchemy import DateTime, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy.types import TypeDecorator


class Base(DeclarativeBase):
    pass


class DecimalText(TypeDecorator[Decimal]):
    """Store exact decimals as canonical TEXT values in SQLite."""

    impl = Text
    cache_ok = True

    def process_bind_param(self, value: Decimal | str | None, dialect: Any) -> str | None:
        if value is None:
            return None
        return format(Decimal(value), "f")

    def process_result_value(self, value: str | None, dialect: Any) -> Decimal | None:
        return None if value is None else Decimal(value)


class Trade(Base):
    __tablename__ = "trades"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    instrument: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    market: Mapped[str | None] = mapped_column(String(20), nullable=True)
    direction: Mapped[str] = mapped_column(String(5), nullable=False)
    opened_at: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    closed_at: Mapped[str | None] = mapped_column(String(40), nullable=True, index=True)
    entry_price: Mapped[Decimal] = mapped_column(DecimalText(), nullable=False)
    exit_price: Mapped[Decimal | None] = mapped_column(DecimalText(), nullable=True)
    size: Mapped[Decimal] = mapped_column(DecimalText(), nullable=False)
    multiplier: Mapped[Decimal] = mapped_column(DecimalText(), nullable=False)
    fees: Mapped[Decimal] = mapped_column(DecimalText(), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False, index=True)
    realized_pnl_override: Mapped[Decimal | None] = mapped_column(DecimalText(), nullable=True)
    strategy: Mapped[str | None] = mapped_column(String(120), nullable=True, index=True)
    tags: Mapped[str] = mapped_column(Text, nullable=False, default="")
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[str] = mapped_column(String(40), nullable=False)
    updated_at: Mapped[str] = mapped_column(String(40), nullable=False)
