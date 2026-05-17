from __future__ import annotations

from pydantic import BaseModel


class LiquidityLevel(BaseModel):
    label: str
    timeframe: str
    liquidity_type: str
    direction: str
    price: float
    score: int | None = None
    confidence: str | None = None
