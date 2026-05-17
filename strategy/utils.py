from __future__ import annotations

from datetime import datetime, timezone
from typing import Iterable


def parse_time(value: str | datetime) -> datetime:
    if isinstance(value, datetime):
        dt = value
    else:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def sort_candles(candles: Iterable[dict]) -> list[dict]:
    normalized = []
    for candle in candles:
        item = dict(candle)
        item["time"] = parse_time(item.get("time_utc") or item.get("time"))
        normalized.append(item)
    return sorted(normalized, key=lambda c: c["time"])


def closed_at_or_before(candles: Iterable[dict], analysis_as_of: str | datetime) -> list[dict]:
    as_of = parse_time(analysis_as_of)
    return [c for c in sort_candles(candles) if c["time"] <= as_of]


def avg(values: list[float]) -> float:
    return sum(values) / len(values) if values else 0.0


def avg_range(candles: list[dict], window: int = 14) -> float:
    sample = candles[-window:] if len(candles) >= window else candles
    return avg([float(c["high"]) - float(c["low"]) for c in sample])


def avg_body(candles: list[dict], window: int = 10) -> float:
    sample = candles[-window:] if len(candles) >= window else candles
    return avg([abs(float(c["close"]) - float(c["open"])) for c in sample])


def price_position(price: float, low: float, high: float, equilibrium_band_pct: float = 5) -> str:
    if high <= low:
        return "unknown"
    eq = (high + low) / 2
    band = (high - low) * equilibrium_band_pct / 100
    if abs(price - eq) <= band:
        return "equilibrium"
    return "premium" if price > eq else "discount"

