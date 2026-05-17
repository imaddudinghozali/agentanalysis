from __future__ import annotations

from datetime import datetime, timezone
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


ALLOWED_SYMBOLS = {"XAUUSD", "XAGUSD", "DXY"}
ALLOWED_TIMEFRAMES = {"M5", "M15", "H1", "H4", "D1"}


def normalize_utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.tzinfo.utcoffset(value) is None:
        raise ValueError("timestamp must include timezone information")
    return value.astimezone(timezone.utc).replace(microsecond=0)


class CandlePayload(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    symbol: str
    timeframe: str
    time: datetime
    open: float = Field(gt=0)
    high: float = Field(gt=0)
    low: float = Field(gt=0)
    close: float = Field(gt=0)
    volume: float | None = Field(default=None, ge=0)

    @field_validator("symbol")
    @classmethod
    def validate_symbol(cls, value: str) -> str:
        normalized = value.upper()
        if normalized not in ALLOWED_SYMBOLS:
            raise ValueError(f"unsupported symbol: {value}")
        return normalized

    @field_validator("timeframe")
    @classmethod
    def validate_timeframe(cls, value: str) -> str:
        normalized = value.upper()
        if normalized not in ALLOWED_TIMEFRAMES:
            raise ValueError(f"unsupported timeframe: {value}")
        return normalized

    @field_validator("time")
    @classmethod
    def validate_time(cls, value: datetime) -> datetime:
        return normalize_utc(value)

    @model_validator(mode="after")
    def validate_ohlc(self) -> "CandlePayload":
        if self.high < max(self.open, self.close, self.low):
            raise ValueError("high must be greater than or equal to open, low, and close")
        if self.low > min(self.open, self.close, self.high):
            raise ValueError("low must be less than or equal to open, high, and close")
        return self


class IngestionStatus(BaseModel):
    status: Literal["upserted"]
    symbol: str
    timeframe: str
    time_utc: datetime
    source: str


class CSVImportResult(BaseModel):
    status: Literal["imported"]
    symbol: str
    timeframe: str
    rows_imported: int
    rows_rejected: int
    source: str
    errors: list[str] = Field(default_factory=list)
