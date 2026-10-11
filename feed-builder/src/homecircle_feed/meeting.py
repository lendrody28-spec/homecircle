"""Normalized meeting records. Personal contact fields are not part of this shape."""

from __future__ import annotations

from typing import Any

MEETING_KEYS = (
    "id",
    "fellowship",
    "name",
    "schedule",
    "format",
    "location",
    "online",
    "tags",
    "notes",
    "source",
)


def meeting_record(
    *,
    id: str,
    fellowship: str,
    name: str,
    weekday: int,
    day: str,
    start: str,
    timezone: str,
    timezone_source: str,
    duration_minutes: int,
    format: str,
    location_name: str | None,
    address: str | None,
    suburb: str | None,
    state: str | None,
    postal_code: str | None,
    country: str,
    latitude: float | None,
    longitude: float | None,
    approximate: bool,
    online_url: str | None,
    online_phone: str | None,
    tags: list[str],
    notes: str | None,
    source_id: str,
    source_name: str,
    source_url: str,
    record_url: str | None,
    last_seen: str,
) -> dict[str, Any]:
    return {
        "id": id,
        "fellowship": fellowship,
        "name": name,
        "schedule": {
            "day": day,
            "weekday": weekday,
            "start": start,
            "timezone": timezone,
            "timezone_source": timezone_source,
            "duration_minutes": duration_minutes,
        },
        "format": format,
        "location": {
            "name": location_name,
            "address": address,
            "suburb": suburb,
            "state": state,
            "postal_code": postal_code,
            "country": country,
            "latitude": latitude,
            "longitude": longitude,
            "approximate": approximate,
        },
        "online": {"url": online_url, "phone": online_phone},
        "tags": tags,
        "notes": notes,
        "source": {
            "id": source_id,
            "name": source_name,
            "url": source_url,
            "record_url": record_url,
            "last_seen": last_seen,
        },
    }


def comparable(meeting: dict[str, Any]) -> dict[str, Any]:
    """Fields whose change should show up in the daily report. last_seen is excluded."""
    return {
        "name": meeting.get("name"),
        "fellowship": meeting.get("fellowship"),
        "schedule": meeting.get("schedule"),
        "format": meeting.get("format"),
        "location": meeting.get("location"),
        "online": meeting.get("online"),
        "tags": meeting.get("tags"),
        "notes": meeting.get("notes"),
    }
