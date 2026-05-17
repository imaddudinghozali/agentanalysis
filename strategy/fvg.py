from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

from .common import Candle, StrategyConfig


@dataclass(frozen=True)
class FVGSignal:
    detected: bool
    direction: str | None = None
    start_index: int | None = None
    end_index: int | None = None
    lower: float | None = None
    upper: float | None = None
    created_time: object | None = None


def detect_fvg(candles: Sequence[Candle], config: StrategyConfig, direction: str | None = None) -> FVGSignal:
    if len(candles) < 3:
        return FVGSignal(False)
    start = max(2, len(candles) - config.structure_lookback)
    latest: FVGSignal | None = None
    for index in range(start, len(candles)):
        first = candles[index - 2]
        third = candles[index]
        if third.low > first.high and third.low - first.high >= config.fvg_min_size_ticks:
            signal = FVGSignal(True, "bullish", index - 2, index, first.high, third.low, third.time)
            if direction in (None, "bullish"):
                latest = signal
        if third.high < first.low and first.low - third.high >= config.fvg_min_size_ticks:
            signal = FVGSignal(True, "bearish", index - 2, index, third.high, first.low, third.time)
            if direction in (None, "bearish"):
                latest = signal
    return latest or FVGSignal(False)
