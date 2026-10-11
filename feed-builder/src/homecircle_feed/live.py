"""On-device schedule math. Swift and Kotlin samples follow this module.

A meeting is a weekly local-time event. "Now" is an absolute instant. The
device timezone does not matter: the meeting's IANA zone does.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta
from typing import Any, Callable
from zoneinfo import ZoneInfo

from homecircle_feed import SOON_WINDOW_MINUTES


class FeedUnavailable(Exception):
    """Raised when the network fetch fails and there is no cached feed."""


def local_weekday(moment: datetime) -> int:
    """Sunday=0 … Saturday=6, matching the feed."""
    return (moment.weekday() + 1) % 7


def _zone(meeting: dict[str, Any]) -> ZoneInfo:
    name = meeting["schedule"]["timezone"]
    return ZoneInfo(name)


def occurrence_start(meeting: dict[str, Any], now: datetime) -> datetime:
    """Start of the current or next occurrence, in the meeting timezone."""
    if now.tzinfo is None:
        raise ValueError("now must be timezone-aware")
    zone = _zone(meeting)
    local_now = now.astimezone(zone)
    hour, minute = (int(part) for part in meeting["schedule"]["start"].split(":"))
    weekday = int(meeting["schedule"]["weekday"])
    days_ahead = (weekday - local_weekday(local_now)) % 7
    start = local_now.replace(hour=hour, minute=minute, second=0, microsecond=0) + timedelta(days=days_ahead)
    if start <= local_now:
        return start
    # days_ahead == 0 and start > now means later today, which is the next start.
    # If we need the occurrence that may already be in progress from last week,
    # callers use in_progress_start.
    return start


def in_progress_start(meeting: dict[str, Any], now: datetime) -> datetime:
    """The most recent start at or before now. May be on an earlier weekday."""
    if now.tzinfo is None:
        raise ValueError("now must be timezone-aware")
    zone = _zone(meeting)
    local_now = now.astimezone(zone)
    hour, minute = (int(part) for part in meeting["schedule"]["start"].split(":"))
    weekday = int(meeting["schedule"]["weekday"])
    days_back = (local_weekday(local_now) - weekday) % 7
    start = local_now.replace(hour=hour, minute=minute, second=0, microsecond=0) - timedelta(days=days_back)
    if start > local_now:
        start -= timedelta(days=7)
    return start


def is_live(meeting: dict[str, Any], now: datetime) -> bool:
    start = in_progress_start(meeting, now)
    end = start + timedelta(minutes=int(meeting["schedule"]["duration_minutes"]))
    local_now = now.astimezone(start.tzinfo)
    return start <= local_now < end


def starts_soon(meeting: dict[str, Any], now: datetime, window_minutes: int = SOON_WINDOW_MINUTES) -> bool:
    if is_live(meeting, now):
        return False
    start = occurrence_start(meeting, now)
    local_now = now.astimezone(start.tzinfo)
    delta = start - local_now
    return timedelta(0) < delta <= timedelta(minutes=window_minutes)


def classify(
    meetings: list[dict[str, Any]],
    now: datetime,
    window_minutes: int = SOON_WINDOW_MINUTES,
) -> dict[str, list[dict[str, Any]]]:
    live: list[dict[str, Any]] = []
    soon: list[dict[str, Any]] = []
    for meeting in meetings:
        if is_live(meeting, now):
            live.append(meeting)
        elif starts_soon(meeting, now, window_minutes):
            soon.append(meeting)
    return {"live": live, "starting_soon": soon}


def load_feed(
    fetch: Callable[[], str],
    read_cache: Callable[[], str | None],
    write_cache: Callable[[str], None],
) -> tuple[dict[str, Any], str]:
    """Fetch on open. If the network fails, return the cached JSON.

    Returns (payload, "network" | "cache").
    """
    try:
        body = fetch()
    except Exception:
        cached = read_cache()
        if not cached:
            raise FeedUnavailable("Meeting feed is unreachable and no cache is stored.") from None
        return json.loads(cached), "cache"
    write_cache(body)
    return json.loads(body), "network"
