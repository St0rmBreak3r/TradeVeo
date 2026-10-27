from __future__ import annotations

import math
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

Decision = Literal["LONG", "SHORT", "NO_TRADE"]
Confidence = Literal["low", "medium", "high"]


class EntryZone(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    low: float | None = None
    high: float | None = None
    basis: str | None = Field(default=None, max_length=500)

    @model_validator(mode="after")
    def validate_zone(self) -> "EntryZone":
        for level in (self.low, self.high):
            if level is not None and (not math.isfinite(level) or level <= 0):
                raise ValueError("Entry prices must be finite positive numbers.")
        if self.low is not None and self.high is not None and self.low > self.high:
            raise ValueError("Entry zone low must not exceed high.")
        return self


class PriceLevel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    price: float = Field(gt=0)
    basis: str = Field(min_length=1, max_length=500)

    @model_validator(mode="after")
    def finite_price(self) -> "PriceLevel":
        if not math.isfinite(self.price):
            raise ValueError("Price must be finite.")
        return self


class ChartAnalysisResult(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    decision: Decision
    symbol: str | None = Field(default=None, max_length=40)
    timeframe: str | None = Field(default=None, max_length=40)
    setup_type: str | None = Field(default=None, max_length=100)
    entry: EntryZone | None = None
    stop_loss: PriceLevel | None = None
    targets: list[PriceLevel] = Field(default_factory=list, max_length=5)
    confidence: Confidence
    confidence_note: str = Field(min_length=1, max_length=1000)
    observations: list[str] = Field(default_factory=list, max_length=8)
    rationale: str = Field(min_length=1, max_length=2000)
    invalidation: str | None = Field(default=None, max_length=1000)
    warnings: list[str] = Field(default_factory=list, max_length=8)

    @model_validator(mode="after")
    def no_actionable_levels_without_signal(self) -> "ChartAnalysisResult":
        if self.decision == "NO_TRADE" and (self.entry is not None or self.stop_loss is not None or self.targets):
            raise ValueError("NO_TRADE results must not include actionable entry, stop, or targets.")
        return self
