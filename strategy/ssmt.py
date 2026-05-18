from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Sequence

from .common import Candle, StrategyConfig, parse_time


@dataclass(frozen=True)
class SSMTSignal:
    available: bool
    detected: bool
    type: str | None = None
    quality: str = "unavailable"
    sync_status: str = "secondary_missing"
    divergence_time: object | None = None
    primary_price: float | None = None
    secondary_price: float | None = None
    sequence: str | None = None
    primary_quarter: str | None = None
    reference_quarter: str | None = None
    magneto: bool = False
    magneto_level: float | None = None
    warning: str | None = None


def detect_ssmt(
    primary: Sequence[Candle],
    secondary: Sequence[Candle] | None,
    analysis_as_of: Any,
    config: StrategyConfig,
    lookback: int = 20,
) -> SSMTSignal:
    as_of = parse_time(analysis_as_of)
    if not primary:
        return SSMTSignal(False, False, sync_status="insufficient_data", warning="INSUFFICIENT_DATA")
    if not secondary:
        return SSMTSignal(False, False, sync_status="secondary_missing", warning="SSMT_UNAVAILABLE")
    if len(primary) < 3 or len(secondary) < 3:
        return SSMTSignal(False, False, sync_status="insufficient_data", warning="SSMT_UNAVAILABLE")
    primary_latest = primary[-1]
    secondary_latest = secondary[-1]
    stale_minutes = (as_of - secondary_latest.time).total_seconds() / 60.0
    if stale_minutes > config.secondary_stale_after_minutes:
        return SSMTSignal(False, False, sync_status="secondary_stale", warning="SECONDARY_STALE")
    mismatch_minutes = abs((primary_latest.time - secondary_latest.time).total_seconds()) / 60.0
    if mismatch_minutes > config.ssmt_alignment_tolerance_minutes:
        return SSMTSignal(False, False, sync_status="timestamp_mismatch", warning="SSMT_TIMESTAMP_MISMATCH")
    secondary_index_by_time = {c.time: index for index, c in enumerate(secondary)}
    scan_start = max(1, len(primary) - lookback)
    magneto_candidate: SSMTSignal | None = None
    for primary_index in range(len(primary) - 1, scan_start - 1, -1):
        p_last = primary[primary_index]
        secondary_index = secondary_index_by_time.get(p_last.time)
        if secondary_index is None:
            continue
        if secondary_index < 1:
            continue
        s_last = secondary[secondary_index]
        p_prev = list(primary[max(0, primary_index - lookback) : primary_index])
        s_prev = list(secondary[max(0, secondary_index - lookback) : secondary_index])
        if len(p_prev) < 2 or len(s_prev) < 2:
            continue
        primary_low_ref = min(p_prev, key=lambda candle: candle.low)
        secondary_low_ref = min(s_prev, key=lambda candle: candle.low)
        primary_high_ref = max(p_prev, key=lambda candle: candle.high)
        secondary_high_ref = max(s_prev, key=lambda candle: candle.high)
        primary_lower_low = p_last.low < primary_low_ref.low
        secondary_lower_low = s_last.low < secondary_low_ref.low
        primary_higher_high = p_last.high > primary_high_ref.high
        secondary_higher_high = s_last.high > secondary_high_ref.high
        if primary_lower_low and p_last.close > primary_low_ref.low and not secondary_lower_low:
            signal = _build_signal(
                "bullish",
                p_last,
                s_last,
                p_last.low,
                s_last.low,
                primary_low_ref.time,
                _delivery_level("bullish", p_prev),
                primary[primary_index + 1 :],
            )
            if signal.detected:
                return signal
            magneto_candidate = magneto_candidate or signal
        if primary_higher_high and p_last.close < primary_high_ref.high and not secondary_higher_high:
            signal = _build_signal(
                "bearish",
                p_last,
                s_last,
                p_last.high,
                s_last.high,
                primary_high_ref.time,
                _delivery_level("bearish", p_prev),
                primary[primary_index + 1 :],
            )
            if signal.detected:
                return signal
            magneto_candidate = magneto_candidate or signal
    if magneto_candidate is not None:
        return magneto_candidate
    return SSMTSignal(True, False, None, "none", "aligned")


def _build_signal(
    ssmt_type: str,
    primary_candle: Candle,
    secondary_candle: Candle,
    primary_price: float,
    secondary_price: float,
    reference_time: datetime,
    magneto_level: float,
    future_primary: Sequence[Candle],
) -> SSMTSignal:
    reference_quarter = _quarter_label(reference_time)
    primary_quarter = _quarter_label(primary_candle.time)
    if not _is_next_quarter(reference_time, primary_candle.time):
        return SSMTSignal(
            True,
            False,
            ssmt_type,
            "none",
            "non_sequential_quarter",
            primary_candle.time,
            primary_price,
            secondary_price,
            "non_sequential",
            primary_quarter,
            reference_quarter,
        )
    if _is_magneto(ssmt_type, future_primary, magneto_level):
        return SSMTSignal(
            True,
            False,
            ssmt_type,
            "magneto",
            "magneto",
            primary_candle.time,
            primary_price,
            secondary_price,
            "sequential",
            primary_quarter,
            reference_quarter,
            True,
            magneto_level,
        )
    return SSMTSignal(
        True,
        True,
        ssmt_type,
        "high",
        "aligned",
        primary_candle.time,
        primary_price,
        secondary_price,
        "sequential",
        primary_quarter,
        reference_quarter,
        False,
        magneto_level,
    )


def _delivery_level(ssmt_type: str, previous: Sequence[Candle]) -> float:
    if ssmt_type == "bullish":
        return max(candle.high for candle in previous)
    return min(candle.low for candle in previous)


def _is_magneto(ssmt_type: str, future_primary: Sequence[Candle], magneto_level: float) -> bool:
    if ssmt_type == "bullish":
        return any(candle.high >= magneto_level for candle in future_primary)
    return any(candle.low <= magneto_level for candle in future_primary)


def _quarter_label(value: datetime) -> str:
    dt = value.astimezone(timezone.utc)
    quarter = dt.hour // 6 + 1
    return f"{dt.date().isoformat()}Q{quarter}"


def _is_next_quarter(reference: datetime, current: datetime) -> bool:
    ref_start = _quarter_start(reference)
    current_start = _quarter_start(current)
    return current_start - ref_start == timedelta(hours=6)


def _quarter_start(value: datetime) -> datetime:
    dt = value.astimezone(timezone.utc)
    hour = (dt.hour // 6) * 6
    return datetime(dt.year, dt.month, dt.day, hour, tzinfo=timezone.utc)
