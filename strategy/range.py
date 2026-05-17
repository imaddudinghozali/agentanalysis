from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping, Sequence

from .common import Candle, StrategyConfig, timeframe_swing_params
from .swing import SwingPoint, detect_swings


@dataclass(frozen=True)
class DealingRange:
    timeframe: str
    high: float
    low: float
    high_time: object
    low_time: object
    equilibrium: float
    current_position: str
    current_price: float
    direction_hint: str


def classify_position(price: float, low: float, high: float, equilibrium_band_pct: float = 5.0) -> str:
    if high <= low:
        return "unknown"
    equilibrium = (high + low) / 2.0
    band = (high - low) * (equilibrium_band_pct / 100.0)
    if abs(price - equilibrium) <= band:
        return "equilibrium"
    return "premium" if price > equilibrium else "discount"


def build_active_dealing_range(
    candles_by_timeframe: Mapping[str, Sequence[Candle]],
    config: StrategyConfig,
    prefer: Sequence[str] = ("H4", "H1"),
    current_price: float | None = None,
) -> tuple[DealingRange | None, dict[str, list[SwingPoint]]]:
    swings_by_tf: dict[str, list[SwingPoint]] = {}
    for timeframe, candles in candles_by_timeframe.items():
        if current_price is None and candles:
            current_price = candles[-1].close
        left, right, major_filter = timeframe_swing_params(timeframe, config)
        swings_by_tf[timeframe.upper()] = detect_swings(
            candles, left=left, right=right, timeframe=timeframe.upper(), min_atr_distance=major_filter
        )
    if current_price is None:
        return None, swings_by_tf
    for timeframe in prefer:
        range_ = _range_for_timeframe(timeframe.upper(), swings_by_tf.get(timeframe.upper(), []), current_price, config)
        if range_ is not None:
            return range_, swings_by_tf
    return None, swings_by_tf


def _range_for_timeframe(
    timeframe: str,
    swings: Sequence[SwingPoint],
    current_price: float,
    config: StrategyConfig,
) -> DealingRange | None:
    highs = [swing for swing in swings if swing.kind == "high"]
    lows = [swing for swing in swings if swing.kind == "low"]
    pairs: list[tuple[int, SwingPoint, SwingPoint]] = []
    for high in highs:
        for low in lows:
            if low.price <= current_price <= high.price:
                pairs.append((max(high.index, low.index), high, low))
    if not pairs:
        return None
    _, high, low = max(pairs, key=lambda item: item[0])
    equilibrium = (high.price + low.price) / 2.0
    position = classify_position(current_price, low.price, high.price, config.equilibrium_band_pct)
    return DealingRange(
        timeframe=timeframe,
        high=high.price,
        low=low.price,
        high_time=high.time,
        low_time=low.time,
        equilibrium=equilibrium,
        current_position=position,
        current_price=current_price,
        direction_hint=_direction_from_position(position),
    )


def _direction_from_position(position: str) -> str:
    if position == "premium":
        return "sellside"
    if position == "discount":
        return "buyside"
    return "neutral"
