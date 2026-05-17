from __future__ import annotations

from dataclasses import asdict, dataclass, field, is_dataclass
from datetime import datetime, timezone
from typing import Any, Iterable, Mapping, Optional, Sequence


RULE_VERSION = "mvp-0.1"


@dataclass(frozen=True)
class Candle:
    time: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float = 0.0

    @property
    def body(self) -> float:
        return abs(self.close - self.open)

    @property
    def direction(self) -> str:
        if self.close > self.open:
            return "bullish"
        if self.close < self.open:
            return "bearish"
        return "neutral"


@dataclass(frozen=True)
class StrategyConfig:
    swing_left_bars_m15: int = 2
    swing_right_bars_m15: int = 2
    swing_left_bars_h1: int = 3
    swing_right_bars_h1: int = 3
    swing_left_bars_h4: int = 3
    swing_right_bars_h4: int = 3
    swing_left_bars_d1: int = 2
    swing_right_bars_d1: int = 2
    equal_high_low_tolerance_pct: float = 0.05
    sweep_buffer_ticks: float = 0.1
    ssmt_alignment_tolerance_minutes: int = 1
    secondary_stale_after_minutes: int = 15
    displacement_body_atr_multiplier: float = 1.5
    fvg_min_size_ticks: float = 0.1
    equilibrium_band_pct: float = 5.0
    minimum_htf_candles_h1: int = 120
    minimum_htf_candles_h4: int = 80
    minimum_htf_candles_d1: int = 30
    minimum_m15_candles: int = 200
    displacement_lookback: int = 20
    sweep_lookback: int = 16
    structure_lookback: int = 30


@dataclass(frozen=True)
class DataCoverage:
    status: str
    missing: list[str] = field(default_factory=list)
    stale: list[str] = field(default_factory=list)
    degraded_mode: bool = False
    warnings: list[str] = field(default_factory=list)
    counts: dict[str, int] = field(default_factory=dict)
    last_candles: dict[str, str] = field(default_factory=dict)


def parse_time(value: Any) -> datetime:
    if isinstance(value, datetime):
        dt = value
    elif isinstance(value, (int, float)):
        dt = datetime.fromtimestamp(value, tz=timezone.utc)
    elif isinstance(value, str):
        text = value.strip()
        if text.endswith("Z"):
            text = text[:-1] + "+00:00"
        dt = datetime.fromisoformat(text)
    else:
        raise TypeError(f"Unsupported candle time value: {value!r}")
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def to_candle(raw: Candle | Mapping[str, Any]) -> Candle:
    if isinstance(raw, Candle):
        return raw
    time_value = raw.get("time", raw.get("time_utc"))
    if time_value is None:
        raise ValueError("Candle is missing time/time_utc")
    return Candle(
        time=parse_time(time_value),
        open=float(raw["open"]),
        high=float(raw["high"]),
        low=float(raw["low"]),
        close=float(raw["close"]),
        volume=float(raw.get("volume", 0.0) or 0.0),
    )


def normalize_candles(
    candles: Optional[Iterable[Candle | Mapping[str, Any]]],
    analysis_as_of: Any | None = None,
) -> list[Candle]:
    as_of = parse_time(analysis_as_of) if analysis_as_of is not None else None
    normalized = [to_candle(candle) for candle in (candles or [])]
    if as_of is not None:
        normalized = [candle for candle in normalized if candle.time <= as_of]
    return sorted(normalized, key=lambda candle: candle.time)


def true_ranges(candles: Sequence[Candle]) -> list[float]:
    ranges: list[float] = []
    prev_close: float | None = None
    for candle in candles:
        if prev_close is None:
            ranges.append(candle.high - candle.low)
        else:
            ranges.append(
                max(
                    candle.high - candle.low,
                    abs(candle.high - prev_close),
                    abs(candle.low - prev_close),
                )
            )
        prev_close = candle.close
    return ranges


def average_true_range(candles: Sequence[Candle], period: int = 14) -> float:
    if not candles:
        return 0.0
    values = true_ranges(candles[-period:])
    return sum(values) / len(values) if values else 0.0


def average_body(candles: Sequence[Candle], period: int = 20) -> float:
    window = list(candles[-period:])
    if not window:
        return 0.0
    return sum(candle.body for candle in window) / len(window)


def confidence_from_score(score: int) -> str:
    if score >= 80:
        return "high"
    if score >= 60:
        return "medium"
    if score >= 40:
        return "low"
    return "unavailable"


def timeframe_swing_params(timeframe: str, config: StrategyConfig) -> tuple[int, int, float]:
    tf = timeframe.upper()
    if tf == "M15":
        return config.swing_left_bars_m15, config.swing_right_bars_m15, 0.25
    if tf == "H1":
        return config.swing_left_bars_h1, config.swing_right_bars_h1, 0.35
    if tf == "H4":
        return config.swing_left_bars_h4, config.swing_right_bars_h4, 0.50
    if tf == "D1":
        return config.swing_left_bars_d1, config.swing_right_bars_d1, 0.50
    return 2, 2, 0.0


def asdict_clean(value: Any) -> Any:
    if is_dataclass(value):
        return asdict_clean(asdict(value))
    if isinstance(value, Mapping):
        return {str(key): asdict_clean(item) for key, item in value.items()}
    if isinstance(value, list):
        return [asdict_clean(item) for item in value]
    if isinstance(value, tuple):
        return [asdict_clean(item) for item in value]
    if isinstance(value, datetime):
        return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
    return value
