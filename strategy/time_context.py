from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from .common import parse_time


@dataclass(frozen=True)
class TimeContext:
    session: str
    killzone: bool
    valid_time: bool


def get_time_context(value: object) -> TimeContext:
    dt = _to_new_york_time(parse_time(value))
    minutes = dt.hour * 60 + dt.minute
    if 2 * 60 <= minutes < 5 * 60:
        return TimeContext("London", True, True)
    if 7 * 60 <= minutes < 10 * 60:
        return TimeContext("New York", True, True)
    if 19 * 60 <= minutes or minutes < 2 * 60:
        return TimeContext("Asia", False, True)
    if 10 * 60 <= minutes < 12 * 60:
        return TimeContext("New York", False, True)
    return TimeContext("Outside major session", False, True)


def _to_new_york_time(dt: datetime) -> datetime:
    try:
        return dt.astimezone(ZoneInfo("America/New_York"))
    except ZoneInfoNotFoundError:
        # Windows Python installs often omit IANA tzdata. This fallback covers
        # US DST well enough for deterministic session classification.
        utc_dt = dt.astimezone(timezone.utc)
        year = utc_dt.year
        dst_start = _nth_weekday(year, 3, 6, 2).replace(hour=7, tzinfo=timezone.utc)
        dst_end = _nth_weekday(year, 11, 6, 1).replace(hour=6, tzinfo=timezone.utc)
        offset_hours = -4 if dst_start <= utc_dt < dst_end else -5
        return utc_dt.astimezone(timezone(timedelta(hours=offset_hours)))


def _nth_weekday(year: int, month: int, weekday: int, occurrence: int) -> datetime:
    first = datetime(year, month, 1)
    days_until = (weekday - first.weekday()) % 7
    return first + timedelta(days=days_until + 7 * (occurrence - 1))
