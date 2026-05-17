from __future__ import annotations

from dataclasses import dataclass, field
from typing import Sequence

from .common import Candle, StrategyConfig
from .range import DealingRange, classify_position
from .swing import SwingPoint


@dataclass(frozen=True)
class HTFFrameState:
    timeframe: str
    status: str
    position: str = "unknown"
    direction: str = "neutral"
    range_high: float | None = None
    range_low: float | None = None
    equilibrium: float | None = None
    reason: str | None = None


@dataclass(frozen=True)
class HTFNarrative:
    status: str
    direction: str | None
    conflict: bool = False
    reason_code: str | None = None
    frames: list[HTFFrameState] = field(default_factory=list)
    reasoning: list[str] = field(default_factory=list)


def build_htf_narrative(
    h1: Sequence[Candle],
    h4: Sequence[Candle],
    d1: Sequence[Candle],
    active_range: DealingRange | None,
    swings_by_tf: dict[str, Sequence[SwingPoint]],
    config: StrategyConfig,
) -> HTFNarrative:
    current_price = _current_price(h1, h4, d1, active_range)
    if current_price is None:
        return HTFNarrative("insufficient", None, reason_code="MISSING_HTF_CONTEXT")

    frames = [
        _swing_frame("H4", h4, swings_by_tf.get("H4", []), current_price, config, config.minimum_htf_candles_h4),
        _swing_frame("H1", h1, swings_by_tf.get("H1", []), current_price, config, config.minimum_htf_candles_h1),
        _daily_frame(d1, current_price, config),
    ]
    usable = [frame for frame in frames if frame.status == "complete" and frame.direction != "neutral"]
    h4_state = next(frame for frame in frames if frame.timeframe == "H4")
    h1_state = next(frame for frame in frames if frame.timeframe == "H1")
    d1_state = next(frame for frame in frames if frame.timeframe == "D1")
    h1_complete = h1_state.status == "complete"
    h4_complete = h4_state.status == "complete"
    required_incomplete = []
    if not h1_complete:
        required_incomplete.append("H1")
    if not h4_complete and not h1_complete:
        required_incomplete.append("H4")
    if required_incomplete:
        return HTFNarrative(
            "insufficient",
            None,
            reason_code="MISSING_HTF_CONTEXT",
            frames=frames,
            reasoning=[f"{', '.join(required_incomplete)} context is incomplete"],
        )
    if not usable:
        return HTFNarrative(
            "neutral",
            None,
            reason_code="UNCLEAR_DOL",
            frames=frames,
            reasoning=["D1/H4/H1 are neutral or unavailable"],
        )

    required_dirs = {frame.direction for frame in (h4_state, h1_state) if frame.direction != "neutral"}
    conflict = len(required_dirs) > 1
    anchor_state = h4_state if h4_state.direction != "neutral" else h1_state
    if d1_state.status == "complete" and d1_state.direction != "neutral" and anchor_state.direction != "neutral":
        conflict = conflict or d1_state.direction != anchor_state.direction
    if conflict:
        return HTFNarrative(
            "conflict",
            None,
            conflict=True,
            reason_code="HTF_CONFLICT",
            frames=frames,
            reasoning=[f"{frame.timeframe} points {frame.direction}" for frame in usable],
        )

    direction = h4_state.direction if h4_state.direction != "neutral" else h1_state.direction
    if direction == "neutral" and d1_state.status == "complete":
        direction = d1_state.direction
    return HTFNarrative(
        "complete" if h4_complete else "degraded",
        direction,
        frames=frames,
        reasoning=[f"{frame.timeframe} {frame.position} favors {frame.direction}" for frame in usable],
    )


def _current_price(
    h1: Sequence[Candle],
    h4: Sequence[Candle],
    d1: Sequence[Candle],
    active_range: DealingRange | None,
) -> float | None:
    if active_range is not None:
        return active_range.current_price
    for candles in (h1, h4, d1):
        if candles:
            return candles[-1].close
    return None


def _daily_frame(d1: Sequence[Candle], current_price: float, config: StrategyConfig) -> HTFFrameState:
    if len(d1) < config.minimum_htf_candles_d1 or len(d1) < 2:
        return HTFFrameState("D1", "unavailable", reason="D1_MISSING")
    previous = d1[-2]
    position = classify_position(current_price, previous.low, previous.high, config.equilibrium_band_pct)
    return HTFFrameState(
        "D1",
        "complete",
        position=position,
        direction=_direction_from_position(position),
        range_high=previous.high,
        range_low=previous.low,
        equilibrium=(previous.high + previous.low) / 2.0,
        reason="previous_day_range",
    )


def _swing_frame(
    timeframe: str,
    candles: Sequence[Candle],
    swings: Sequence[SwingPoint],
    current_price: float,
    config: StrategyConfig,
    minimum: int,
) -> HTFFrameState:
    if len(candles) < minimum:
        return HTFFrameState(timeframe, "insufficient", reason=f"{timeframe}_MISSING")
    range_ = _range_from_swings(timeframe, swings, current_price, config)
    if range_ is None:
        return HTFFrameState(timeframe, "no_active_range", reason="NO_ACTIVE_DEALING_RANGE")
    return HTFFrameState(
        timeframe,
        "complete",
        position=range_.current_position,
        direction=range_.direction_hint,
        range_high=range_.high,
        range_low=range_.low,
        equilibrium=range_.equilibrium,
        reason="active_swing_range",
    )


def _range_from_swings(
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
