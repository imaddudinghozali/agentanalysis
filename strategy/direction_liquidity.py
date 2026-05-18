from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Sequence

from .common import Candle, StrategyConfig
from .range import classify_position


@dataclass(frozen=True)
class DirectionLiquidityLevel:
    parent_timeframe: str
    irl_erl_timeframe: str
    direction_timeframes: list[str]
    status: str
    draw_direction: str | None = None
    position: str = "unknown"
    range_high: float | None = None
    range_low: float | None = None
    equilibrium: float | None = None
    reason: str | None = None


@dataclass(frozen=True)
class DirectionLiquidityHierarchy:
    status: str
    active_level: DirectionLiquidityLevel | None = None
    dominant_direction: str | None = None
    levels: list[DirectionLiquidityLevel] = field(default_factory=list)
    reasoning: list[str] = field(default_factory=list)


def build_direction_liquidity_hierarchy(
    *,
    m15: Sequence[Candle],
    h1: Sequence[Candle],
    h4: Sequence[Candle],
    d1: Sequence[Candle],
    m5: Sequence[Candle] | None = None,
    current_price: float | None = None,
    config: StrategyConfig | None = None,
) -> DirectionLiquidityHierarchy:
    cfg = config or StrategyConfig()
    price = current_price or _latest_close(m15, h1, h4, d1, m5 or [])
    if price is None:
        return DirectionLiquidityHierarchy("insufficient", reasoning=["No current price for direction liquidity"])

    weekly = _aggregate_days(d1, "W1")
    monthly = _aggregate_days(d1, "MN")
    levels = [
        _level(
            parent_timeframe="MN",
            irl_erl_timeframe="W1",
            direction_timeframes=["D1"],
            parent_candles=monthly,
            child_candles=weekly,
            current_price=price,
            minimum_parent_candles=2,
            minimum_child_candles=2,
            cfg=cfg,
        ),
        _level(
            parent_timeframe="W1",
            irl_erl_timeframe="D1",
            direction_timeframes=["H4"],
            parent_candles=weekly,
            child_candles=d1,
            current_price=price,
            minimum_parent_candles=2,
            minimum_child_candles=2,
            cfg=cfg,
        ),
        _level(
            parent_timeframe="D1",
            irl_erl_timeframe="H1",
            direction_timeframes=["M15", "M5"],
            parent_candles=d1,
            child_candles=h1,
            current_price=price,
            minimum_parent_candles=2,
            minimum_child_candles=24,
            cfg=cfg,
        ),
    ]
    active = _active_level(levels)
    if active is None:
        return DirectionLiquidityHierarchy(
            "insufficient",
            levels=levels,
            reasoning=["Direction liquidity hierarchy has no complete level"],
        )
    return DirectionLiquidityHierarchy(
        "complete",
        active_level=active,
        dominant_direction=active.draw_direction,
        levels=levels,
        reasoning=[
            f"{active.parent_timeframe} candle uses {active.irl_erl_timeframe} IRL/ERL "
            f"into {', '.join(active.direction_timeframes)} direction liquidity"
        ],
    )


def _level(
    *,
    parent_timeframe: str,
    irl_erl_timeframe: str,
    direction_timeframes: list[str],
    parent_candles: Sequence[Candle],
    child_candles: Sequence[Candle],
    current_price: float,
    minimum_parent_candles: int,
    minimum_child_candles: int,
    cfg: StrategyConfig,
) -> DirectionLiquidityLevel:
    if len(parent_candles) < minimum_parent_candles:
        return DirectionLiquidityLevel(
            parent_timeframe,
            irl_erl_timeframe,
            direction_timeframes,
            "insufficient",
            reason=f"{parent_timeframe}_MISSING",
        )
    if len(child_candles) < minimum_child_candles:
        return DirectionLiquidityLevel(
            parent_timeframe,
            irl_erl_timeframe,
            direction_timeframes,
            "insufficient",
            reason=f"{irl_erl_timeframe}_IRL_ERL_MISSING",
        )

    reference = parent_candles[-2]
    position = classify_position(current_price, reference.low, reference.high, cfg.equilibrium_band_pct)
    return DirectionLiquidityLevel(
        parent_timeframe=parent_timeframe,
        irl_erl_timeframe=irl_erl_timeframe,
        direction_timeframes=direction_timeframes,
        status="complete",
        draw_direction=_direction_from_position(position),
        position=position,
        range_high=reference.high,
        range_low=reference.low,
        equilibrium=(reference.high + reference.low) / 2.0,
        reason="previous_candle_liquidity",
    )


def _active_level(levels: Sequence[DirectionLiquidityLevel]) -> DirectionLiquidityLevel | None:
    for timeframe in ("D1", "W1", "MN"):
        for level in levels:
            if level.parent_timeframe == timeframe and level.status == "complete" and level.draw_direction != "neutral":
                return level
    return next((level for level in levels if level.status == "complete"), None)


def _aggregate_days(candles: Sequence[Candle], timeframe: str) -> list[Candle]:
    if not candles:
        return []
    buckets: dict[datetime, list[Candle]] = {}
    for candle in candles:
        key = _bucket_start(candle.time, timeframe)
        buckets.setdefault(key, []).append(candle)
    aggregated: list[Candle] = []
    for key in sorted(buckets):
        items = sorted(buckets[key], key=lambda candle: candle.time)
        aggregated.append(
            Candle(
                time=key,
                open=items[0].open,
                high=max(item.high for item in items),
                low=min(item.low for item in items),
                close=items[-1].close,
                volume=sum(item.volume for item in items),
            )
        )
    return aggregated


def _bucket_start(value: datetime, timeframe: str) -> datetime:
    dt = value.astimezone(timezone.utc)
    if timeframe == "W1":
        start = dt - timedelta(days=dt.weekday())
        return datetime(start.year, start.month, start.day, tzinfo=timezone.utc)
    if timeframe == "MN":
        return datetime(dt.year, dt.month, 1, tzinfo=timezone.utc)
    raise ValueError(f"unsupported aggregate timeframe: {timeframe}")


def _latest_close(*series: Sequence[Candle]) -> float | None:
    latest: Candle | None = None
    for candles in series:
        if candles and (latest is None or candles[-1].time > latest.time):
            latest = candles[-1]
    return latest.close if latest else None


def _direction_from_position(position: str) -> str:
    if position == "premium":
        return "sellside"
    if position == "discount":
        return "buyside"
    return "neutral"
