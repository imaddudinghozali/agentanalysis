from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
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
        primary_lower_low = p_last.low < min(c.low for c in p_prev)
        secondary_lower_low = s_last.low < min(c.low for c in s_prev)
        primary_higher_high = p_last.high > max(c.high for c in p_prev)
        secondary_higher_high = s_last.high > max(c.high for c in s_prev)
        if primary_lower_low and not secondary_lower_low:
            return SSMTSignal(True, True, "bullish", "medium", "aligned", p_last.time, p_last.low, s_last.low)
        if primary_higher_high and not secondary_higher_high:
            return SSMTSignal(True, True, "bearish", "medium", "aligned", p_last.time, p_last.high, s_last.high)
    return SSMTSignal(True, False, None, "none", "aligned")
