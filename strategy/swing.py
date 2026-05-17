from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

from .common import Candle, average_true_range


@dataclass(frozen=True)
class SwingPoint:
    index: int
    time: object
    price: float
    kind: str
    timeframe: str
    major: bool = True


def detect_swings(
    candles: Sequence[Candle],
    left: int = 2,
    right: int = 2,
    timeframe: str = "M15",
    min_atr_distance: float = 0.0,
) -> list[SwingPoint]:
    if len(candles) < left + right + 1:
        return []
    atr = average_true_range(candles)
    min_distance = atr * min_atr_distance
    swings: list[SwingPoint] = []
    for index in range(left, len(candles) - right):
        candle = candles[index]
        left_side = candles[index - left : index]
        right_side = candles[index + 1 : index + right + 1]
        is_high = all(candle.high > peer.high for peer in left_side + right_side)
        is_low = all(candle.low < peer.low for peer in left_side + right_side)
        if is_high and _far_enough(swings, candle.high, "high", min_distance):
            swings.append(
                SwingPoint(index=index, time=candle.time, price=candle.high, kind="high", timeframe=timeframe)
            )
        if is_low and _far_enough(swings, candle.low, "low", min_distance):
            swings.append(
                SwingPoint(index=index, time=candle.time, price=candle.low, kind="low", timeframe=timeframe)
            )
    return sorted(swings, key=lambda swing: swing.index)


def latest_swing(swings: Sequence[SwingPoint], kind: str) -> SwingPoint | None:
    for swing in reversed(swings):
        if swing.kind == kind:
            return swing
    return None


def _far_enough(swings: Sequence[SwingPoint], price: float, kind: str, min_distance: float) -> bool:
    if min_distance <= 0:
        return True
    previous = latest_swing(swings, kind)
    return previous is None or abs(price - previous.price) >= min_distance
