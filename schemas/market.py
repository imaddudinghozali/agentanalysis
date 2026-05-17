from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator

from .candle import ALLOWED_SYMBOLS, ALLOWED_TIMEFRAMES, normalize_utc


class AnalysisRequest(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    primary_symbol: str = "XAUUSD"
    secondary_symbol: str | None = "XAGUSD"
    execution_timeframe: str = "M15"
    context_timeframes: list[str] = Field(default_factory=lambda: ["H4", "H1", "D1"])
    analysis_as_of: datetime
    mode: str = "normal"

    @field_validator("primary_symbol", "secondary_symbol")
    @classmethod
    def validate_symbol(cls, value: str | None) -> str | None:
        if value is None:
            return value
        normalized = value.upper()
        if normalized not in ALLOWED_SYMBOLS:
            raise ValueError(f"unsupported symbol: {value}")
        return normalized

    @field_validator("execution_timeframe")
    @classmethod
    def validate_execution_timeframe(cls, value: str) -> str:
        normalized = value.upper()
        if normalized not in ALLOWED_TIMEFRAMES:
            raise ValueError(f"unsupported timeframe: {value}")
        return normalized

    @field_validator("context_timeframes")
    @classmethod
    def validate_context_timeframes(cls, value: list[str]) -> list[str]:
        normalized = [item.upper() for item in value]
        invalid = sorted(set(normalized) - ALLOWED_TIMEFRAMES)
        if invalid:
            raise ValueError(f"unsupported context timeframe(s): {', '.join(invalid)}")
        return normalized

    @field_validator("analysis_as_of")
    @classmethod
    def validate_analysis_as_of(cls, value: datetime) -> datetime:
        return normalize_utc(value)
