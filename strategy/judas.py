from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, time
from typing import Sequence

from .common import Candle, StrategyConfig, parse_time
from .time_context import _to_new_york_time


@dataclass(frozen=True)
class JudasSwingContext:
    status: str
    detected: bool = False
    session: str | None = None
    manipulation_direction: str | None = None
    target_direction: str | None = None
    opening_range_high: float | None = None
    opening_range_low: float | None = None
    judas_price: float | None = None
    judas_time: object | None = None
    target_price: float | None = None
    alignment: str = "unknown"
    confidence: str = "unavailable"
    reasoning: list[str] | None = None


def build_judas_swing_context(
    candles: Sequence[Candle],
    analysis_as_of: object,
    draw_direction: str | None,
    config: StrategyConfig,
) -> JudasSwingContext:
    if not candles:
        return JudasSwingContext("insufficient", reasoning=["M15 candles are unavailable for Judas Swing"])
    as_of_ny = _to_new_york_time(parse_time(analysis_as_of))
    window = _session_window(as_of_ny)
    if window is None:
        return JudasSwingContext("outside_judas_window", reasoning=["Current time is outside London/New York Judas windows"])

    session, range_start, range_end, judas_start, judas_end = window
    session_candles = [candle for candle in candles if _same_ny_date(candle.time, as_of_ny)]
    opening_range = [
        candle for candle in session_candles if range_start <= _to_new_york_time(candle.time).time() < range_end
    ]
    if len(opening_range) < 2:
        return JudasSwingContext(
            "awaiting_opening_range",
            session=session,
            reasoning=[f"{session} opening range is not complete"],
        )

    opening_high = max(candle.high for candle in opening_range)
    opening_low = min(candle.low for candle in opening_range)
    judas_candles = [
        candle
        for candle in session_candles
        if judas_start <= _to_new_york_time(candle.time).time() <= judas_end and candle.time <= parse_time(analysis_as_of)
    ]
    if not judas_candles:
        return JudasSwingContext(
            "awaiting_judas_window",
            session=session,
            opening_range_high=opening_high,
            opening_range_low=opening_low,
            reasoning=[f"{session} opening range is built; waiting for Judas window"],
        )

    for candle in reversed(judas_candles):
        if candle.high > opening_high + config.sweep_buffer_ticks and candle.close < opening_high:
            return _detected_context(
                session=session,
                manipulation_direction="buyside",
                target_direction="sellside",
                opening_high=opening_high,
                opening_low=opening_low,
                judas_price=candle.high,
                judas_time=candle.time,
                target_price=opening_low,
                draw_direction=draw_direction,
            )
        if candle.low < opening_low - config.sweep_buffer_ticks and candle.close > opening_low:
            return _detected_context(
                session=session,
                manipulation_direction="sellside",
                target_direction="buyside",
                opening_high=opening_high,
                opening_low=opening_low,
                judas_price=candle.low,
                judas_time=candle.time,
                target_price=opening_high,
                draw_direction=draw_direction,
            )

    return JudasSwingContext(
        "awaiting_judas_sweep",
        session=session,
        opening_range_high=opening_high,
        opening_range_low=opening_low,
        reasoning=[f"{session} opening range is built, but no rejected Judas sweep is confirmed"],
    )


def _detected_context(
    *,
    session: str,
    manipulation_direction: str,
    target_direction: str,
    opening_high: float,
    opening_low: float,
    judas_price: float,
    judas_time: object,
    target_price: float,
    draw_direction: str | None,
) -> JudasSwingContext:
    alignment = "aligned" if draw_direction == target_direction else "counter_context" if draw_direction in {"buyside", "sellside"} else "unconfirmed"
    confidence = "high" if alignment == "aligned" else "medium" if alignment == "unconfirmed" else "low"
    return JudasSwingContext(
        status="judas_confirmed",
        detected=True,
        session=session,
        manipulation_direction=manipulation_direction,
        target_direction=target_direction,
        opening_range_high=opening_high,
        opening_range_low=opening_low,
        judas_price=judas_price,
        judas_time=judas_time,
        target_price=target_price,
        alignment=alignment,
        confidence=confidence,
        reasoning=[
            f"{session} Judas swept {manipulation_direction} liquidity and rejected back into the opening range",
            f"Classic Judas target points {target_direction}",
        ],
    )


def _session_window(dt: datetime) -> tuple[str, time, time, time, time] | None:
    minutes = dt.hour * 60 + dt.minute
    if 2 * 60 <= minutes < 5 * 60:
        return ("London", time(0, 0), time(2, 0), time(2, 0), time(5, 0))
    if 8 * 60 <= minutes < 10 * 60 + 30:
        return ("New York", time(8, 0), time(9, 0), time(9, 0), time(10, 30))
    return None


def _same_ny_date(value: datetime, reference: datetime) -> bool:
    return _to_new_york_time(value).date() == reference.date()
