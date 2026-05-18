from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Sequence

from .common import Candle, parse_time


@dataclass(frozen=True)
class HTFCandlePhase:
    timeframe: str
    pattern: str
    current_leg: str
    open: float
    high: float
    low: float
    close: float
    open_time: datetime
    high_time: datetime
    low_time: datetime
    last_time: datetime
    completed_legs: list[str]
    next_liquidity_hint: str


def build_htf_candle_phase(
    execution_candles: Sequence[Candle],
    analysis_as_of: object,
    timeframe: str = "D1",
) -> HTFCandlePhase | None:
    if not execution_candles:
        return None
    as_of = parse_time(analysis_as_of)
    start = _period_start(as_of, timeframe)
    end = _period_end(start, timeframe)
    period_candles = [candle for candle in execution_candles if start <= candle.time < end]
    if not period_candles:
        return None

    high_index, high_candle = max(enumerate(period_candles), key=lambda item: item[1].high)
    low_index, low_candle = min(enumerate(period_candles), key=lambda item: item[1].low)
    open_price = period_candles[0].open
    close_price = period_candles[-1].close

    if low_index < high_index:
        pattern = "OLHC"
        completed_legs = ["open_to_low", "low_to_high"]
        current_leg = "high_to_close"
        next_liquidity_hint = "downside_rebalance_or_close"
    elif high_index < low_index:
        pattern = "OHLC"
        completed_legs = ["open_to_high", "high_to_low"]
        current_leg = "low_to_close"
        next_liquidity_hint = "upside_rebalance_or_close"
    else:
        pattern = "UNRESOLVED"
        completed_legs = []
        current_leg = "open_to_range"
        next_liquidity_hint = "wait_for_high_low_sequence"

    return HTFCandlePhase(
        timeframe=timeframe.upper(),
        pattern=pattern,
        current_leg=current_leg,
        open=open_price,
        high=high_candle.high,
        low=low_candle.low,
        close=close_price,
        open_time=period_candles[0].time,
        high_time=high_candle.time,
        low_time=low_candle.time,
        last_time=period_candles[-1].time,
        completed_legs=completed_legs,
        next_liquidity_hint=next_liquidity_hint,
    )


def _period_start(value: datetime, timeframe: str) -> datetime:
    dt = value.astimezone(timezone.utc)
    tf = timeframe.upper()
    if tf == "D1":
        return dt.replace(hour=0, minute=0, second=0, microsecond=0)
    if tf == "H4":
        hour = (dt.hour // 4) * 4
        return dt.replace(hour=hour, minute=0, second=0, microsecond=0)
    if tf == "H1":
        return dt.replace(minute=0, second=0, microsecond=0)
    raise ValueError(f"unsupported HTF candle phase timeframe: {timeframe}")


def _period_end(start: datetime, timeframe: str) -> datetime:
    tf = timeframe.upper()
    if tf == "D1":
        return start + timedelta(days=1)
    if tf == "H4":
        return start + timedelta(hours=4)
    if tf == "H1":
        return start + timedelta(hours=1)
    raise ValueError(f"unsupported HTF candle phase timeframe: {timeframe}")
