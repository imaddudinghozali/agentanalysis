from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

from .common import Candle, StrategyConfig
from .liquidity import SweepEvent
from .swing import SwingPoint


@dataclass(frozen=True)
class StructureSignal:
    detected: bool
    direction: str | None = None
    kind: str | None = None
    break_price: float | None = None
    candle_index: int | None = None
    candle_time: object | None = None


def detect_mss(
    candles: Sequence[Candle],
    swings: Sequence[SwingPoint],
    sweep: SweepEvent | None,
    config: StrategyConfig,
) -> StructureSignal:
    if not candles or not swings or sweep is None:
        return StructureSignal(False)
    if sweep.direction == "sellside":
        target_swings = [s for s in swings if s.kind == "high" and s.index < sweep.candle_index]
        direction = "bullish"
    else:
        target_swings = [s for s in swings if s.kind == "low" and s.index < sweep.candle_index]
        direction = "bearish"
    if not target_swings:
        return StructureSignal(False)
    target = target_swings[-1]
    end = min(len(candles), sweep.candle_index + config.structure_lookback + 1)
    for index in range(sweep.candle_index + 1, end):
        candle = candles[index]
        if direction == "bullish" and candle.close > target.price:
            return StructureSignal(True, direction, "MSS", target.price, index, candle.time)
        if direction == "bearish" and candle.close < target.price:
            return StructureSignal(True, direction, "MSS", target.price, index, candle.time)
    return StructureSignal(False)
