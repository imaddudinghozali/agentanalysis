from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, time
from typing import Sequence

from .common import Candle, StrategyConfig, parse_time
from .time_context import _to_new_york_time


@dataclass(frozen=True)
class NineAMModelContext:
    status: str
    active: bool = False
    profile: str | None = None
    direction: str | None = None
    four_hour_open: float | None = None
    previous_block_high: float | None = None
    previous_block_low: float | None = None
    target_price: float | None = None
    alignment: str = "unknown"
    confidence: str = "unavailable"
    reasoning: list[str] | None = None


def build_nine_am_model_context(
    candles: Sequence[Candle],
    analysis_as_of: object,
    draw_direction: str | None,
    config: StrategyConfig,
    target_price: float | None = None,
) -> NineAMModelContext:
    if not candles:
        return NineAMModelContext("insufficient", reasoning=["M15 candles are unavailable for 09AM model"])
    as_of = parse_time(analysis_as_of)
    as_of_ny = _to_new_york_time(as_of)
    minutes = as_of_ny.hour * 60 + as_of_ny.minute
    if not (9 * 60 <= minutes < 13 * 60):
        return NineAMModelContext("outside_09am_window", reasoning=["Current time is outside the 09AM 4H PO3 block"])
    if draw_direction not in {"buyside", "sellside"}:
        return NineAMModelContext("unclear_direction", reasoning=["09AM model needs a clear DOL direction"])

    day_candles = [candle for candle in candles if _to_new_york_time(candle.time).date() == as_of_ny.date()]
    block_01 = _block(day_candles, time(1, 0), time(5, 0), as_of)
    block_05 = _block(day_candles, time(5, 0), time(9, 0), as_of)
    block_09 = _block(day_candles, time(9, 0), time(13, 0), as_of)
    if not block_01 or not block_05 or not block_09:
        return NineAMModelContext("awaiting_4h_blocks", reasoning=["01AM, 05AM, and 09AM blocks are not all available"])

    high_01, low_01 = _high_low(block_01)
    high_05, low_05 = _high_low(block_05)
    high_09, low_09 = _high_low(block_09)
    open_09 = block_09[0].open
    close_09 = block_09[-1].close

    prior_reversal = _swept_and_rejected(block_05, high_01, low_01, draw_direction, config)
    current_reversal = _swept_and_rejected(block_09, high_05, low_05, draw_direction, config)
    current_expansion = _expanded(block_09, high_05, low_05, draw_direction, config)
    prior_expansion = _expanded(block_05, high_01, low_01, draw_direction, config)
    current_continuation = close_09 > open_09 if draw_direction == "buyside" else close_09 < open_09
    target_unfinished = _target_unfinished(close_09, draw_direction, target_price)

    profile: str | None = None
    if current_reversal:
        profile = "reversal_profile"
    elif prior_reversal and current_expansion:
        profile = "expansion_profile"
    elif prior_expansion and current_continuation and target_unfinished:
        profile = "continuation_profile"

    if profile is None:
        return NineAMModelContext(
            "awaiting_09am_profile",
            active=True,
            direction=draw_direction,
            four_hour_open=open_09,
            previous_block_high=high_05,
            previous_block_low=low_05,
            target_price=target_price,
            reasoning=["09AM block is active but no reversal, expansion, or continuation profile is confirmed"],
        )

    return NineAMModelContext(
        "confirmed",
        active=True,
        profile=profile,
        direction=draw_direction,
        four_hour_open=open_09,
        previous_block_high=high_05,
        previous_block_low=low_05,
        target_price=target_price,
        alignment="aligned",
        confidence="high",
        reasoning=[
            f"09AM 4H PO3 confirms {profile.replace('_', ' ')}",
            f"09AM model follows {draw_direction} DOL from the active narrative",
        ],
    )


def _block(candles: Sequence[Candle], start: time, end: time, as_of: datetime) -> list[Candle]:
    return [
        candle
        for candle in candles
        if start <= _to_new_york_time(candle.time).time() < end and candle.time <= as_of
    ]


def _high_low(candles: Sequence[Candle]) -> tuple[float, float]:
    return max(candle.high for candle in candles), min(candle.low for candle in candles)


def _swept_and_rejected(
    candles: Sequence[Candle],
    previous_high: float,
    previous_low: float,
    draw_direction: str,
    config: StrategyConfig,
) -> bool:
    high, low = _high_low(candles)
    close = candles[-1].close
    if draw_direction == "buyside":
        return low < previous_low - config.sweep_buffer_ticks and close > previous_low
    return high > previous_high + config.sweep_buffer_ticks and close < previous_high


def _expanded(
    candles: Sequence[Candle],
    previous_high: float,
    previous_low: float,
    draw_direction: str,
    config: StrategyConfig,
) -> bool:
    high, low = _high_low(candles)
    close = candles[-1].close
    if draw_direction == "buyside":
        return high > previous_high + config.sweep_buffer_ticks and close > previous_high
    return low < previous_low - config.sweep_buffer_ticks and close < previous_low


def _target_unfinished(close: float, draw_direction: str, target_price: float | None) -> bool:
    if target_price is None:
        return True
    if draw_direction == "buyside":
        return close < target_price
    return close > target_price
