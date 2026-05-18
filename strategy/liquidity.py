from __future__ import annotations

from dataclasses import dataclass, field
from typing import Sequence

from .common import Candle, StrategyConfig
from .range import DealingRange
from .swing import SwingPoint


@dataclass(frozen=True)
class LiquidityPool:
    label: str
    timeframe: str
    liquidity_type: str
    direction: str
    price: float
    source: str = "swing"


@dataclass(frozen=True)
class SweepEvent:
    label: str
    timeframe: str
    direction: str
    price: float
    candle_time: object
    candle_index: int
    swept_level_time: object | None = None


@dataclass(frozen=True)
class LiquidityMap:
    pools: list[LiquidityPool] = field(default_factory=list)
    recently_taken: list[SweepEvent] = field(default_factory=list)


def build_liquidity_pools(
    active_range: DealingRange | None,
    swings_by_tf: dict[str, Sequence[SwingPoint]],
    d1_candles: Sequence[Candle] | None = None,
    execution_candles: Sequence[Candle] | None = None,
) -> list[LiquidityPool]:
    pools: list[LiquidityPool] = []
    if active_range is not None:
        pools.append(
            LiquidityPool(
                label="active_range_high",
                timeframe=active_range.timeframe,
                liquidity_type="ERL",
                direction="buyside",
                price=active_range.high,
                source="active_range",
            )
        )
        pools.append(
            LiquidityPool(
                label="active_range_low",
                timeframe=active_range.timeframe,
                liquidity_type="ERL",
                direction="sellside",
                price=active_range.low,
                source="active_range",
            )
        )
    if d1_candles and len(d1_candles) >= 2:
        previous = d1_candles[-2]
        pools.append(
            LiquidityPool("previous_day_high", "D1", "ERL", "buyside", previous.high, "daily")
        )
        pools.append(
            LiquidityPool("previous_day_low", "D1", "ERL", "sellside", previous.low, "daily")
        )
    if execution_candles:
        current_day = _current_day_candles(execution_candles)
        if len(current_day) >= 4:
            current_day_high = max(current_day, key=lambda candle: candle.high)
            current_day_low = min(current_day, key=lambda candle: candle.low)
            pools.append(
                LiquidityPool(
                    "current_day_high",
                    "M15",
                    "ERL",
                    "buyside",
                    current_day_high.high,
                    "current_day",
                )
            )
            pools.append(
                LiquidityPool(
                    "current_day_low",
                    "M15",
                    "ERL",
                    "sellside",
                    current_day_low.low,
                    "current_day",
                )
            )
    for timeframe, swings in swings_by_tf.items():
        for swing in swings[-12:]:
            direction = "buyside" if swing.kind == "high" else "sellside"
            liquidity_type = "ERL" if timeframe in {"H4", "D1"} else "IRL"
            pools.append(
                LiquidityPool(
                    label=f"{timeframe.lower()}_swing_{swing.kind}",
                    timeframe=timeframe,
                    liquidity_type=liquidity_type,
                    direction=direction,
                    price=swing.price,
                )
            )
    return _dedupe_pools(pools)


def _current_day_candles(candles: Sequence[Candle]) -> list[Candle]:
    if not candles:
        return []
    current_date = candles[-1].time.date()
    return [candle for candle in candles if candle.time.date() == current_date]


def detect_sweeps(
    candles: Sequence[Candle],
    swings: Sequence[SwingPoint],
    config: StrategyConfig,
    timeframe: str = "M15",
) -> list[SweepEvent]:
    if not candles or not swings:
        return []
    start = max(0, len(candles) - config.sweep_lookback)
    events: list[SweepEvent] = []
    for candle_index in range(start, len(candles)):
        candle = candles[candle_index]
        for swing in swings:
            if swing.index >= candle_index:
                continue
            if swing.kind == "high" and candle.high > swing.price + config.sweep_buffer_ticks and candle.close < swing.price:
                events.append(
                    SweepEvent(
                        label="internal_buyside_liquidity",
                        timeframe=timeframe,
                        direction="buyside",
                        price=swing.price,
                        candle_time=candle.time,
                        candle_index=candle_index,
                        swept_level_time=swing.time,
                    )
                )
            if swing.kind == "low" and candle.low < swing.price - config.sweep_buffer_ticks and candle.close > swing.price:
                events.append(
                    SweepEvent(
                        label="internal_sellside_liquidity",
                        timeframe=timeframe,
                        direction="sellside",
                        price=swing.price,
                        candle_time=candle.time,
                        candle_index=candle_index,
                        swept_level_time=swing.time,
                    )
                )
    return events


def latest_sweep(events: Sequence[SweepEvent], direction: str | None = None) -> SweepEvent | None:
    for event in reversed(events):
        if direction is None or event.direction == direction:
            return event
    return None


def _dedupe_pools(pools: Sequence[LiquidityPool]) -> list[LiquidityPool]:
    seen: set[tuple[str, str, float, str]] = set()
    unique: list[LiquidityPool] = []
    for pool in pools:
        key = (pool.label, pool.timeframe, round(pool.price, 5), pool.direction)
        if key not in seen:
            seen.add(key)
            unique.append(pool)
    return unique
