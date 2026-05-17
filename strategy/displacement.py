from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

from .common import Candle, StrategyConfig, average_body


@dataclass(frozen=True)
class DisplacementSignal:
    detected: bool
    direction: str | None = None
    candle_index: int | None = None
    candle_time: object | None = None
    body: float = 0.0
    threshold: float = 0.0


def detect_displacement(candles: Sequence[Candle], config: StrategyConfig) -> DisplacementSignal:
    if len(candles) < 3:
        return DisplacementSignal(False)
    start = max(1, len(candles) - config.displacement_lookback)
    best: DisplacementSignal | None = None
    for index in range(start, len(candles)):
        prior = candles[max(0, index - config.displacement_lookback) : index]
        avg_body = average_body(prior, period=config.displacement_lookback)
        threshold = avg_body * config.displacement_body_atr_multiplier
        candle = candles[index]
        if avg_body > 0 and candle.body >= threshold and candle.direction in {"bullish", "bearish"}:
            best = DisplacementSignal(True, candle.direction, index, candle.time, candle.body, threshold)
    return best or DisplacementSignal(False)
