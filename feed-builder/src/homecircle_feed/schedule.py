"""Day and duration parsing shared by the BMLT and TSML parsers."""

from __future__ import annotations

import re

from homecircle_feed import DEFAULT_DURATION_MINUTES

DAY_NAMES = (
    "sunday",
    "monday",
    "tuesday",
    "wednesday",
    "thursday",
    "friday",
    "saturday",
)
CLOCK_RE = re.compile(r"^(\d{1,2}):(\d{2})(?::(\d{2}))?$")


def day_name(weekday: int) -> str:
    return DAY_NAMES[weekday]


def parse_clock(value: object) -> str | None:
    if value is None:
        return None
    match = CLOCK_RE.match(str(value).strip())
    if not match:
        return None
    hour = int(match.group(1))
    minute = int(match.group(2))
    if hour > 23 or minute > 59:
        return None
    return f"{hour:02d}:{minute:02d}"


def duration_from_clock(value: object, default: int = DEFAULT_DURATION_MINUTES) -> int:
    if value is None or str(value).strip() == "":
        return default
    match = CLOCK_RE.match(str(value).strip())
    if not match:
        return default
    hours = int(match.group(1))
    minutes = int(match.group(2))
    total = hours * 60 + minutes
    if total <= 0 or total > 12 * 60:
        return default
    return total


def duration_between(start: str, end: str | None, default: int = DEFAULT_DURATION_MINUTES) -> int:
    if not end:
        return default
    start_clock = parse_clock(start)
    end_clock = parse_clock(end)
    if not start_clock or not end_clock:
        return default
    sh, sm = (int(part) for part in start_clock.split(":"))
    eh, em = (int(part) for part in end_clock.split(":"))
    delta = (eh * 60 + em) - (sh * 60 + sm)
    if delta <= 0:
        delta += 24 * 60
    if delta > 12 * 60:
        return default
    return delta


def bmlt_weekday(value: object) -> int | None:
    """BMLT weekday_tinyint is 1=Sunday … 7=Saturday."""
    try:
        number = int(str(value).strip())
    except (TypeError, ValueError):
        return None
    if 1 <= number <= 7:
        return number - 1
    return None


def tsml_weekday(value: object) -> int | None:
    """Meeting Guide day is 0=Sunday … 6=Saturday."""
    try:
        number = int(str(value).strip())
    except (TypeError, ValueError):
        return None
    if 0 <= number <= 6:
        return number
    return None
