"""Check a feed file before it is written."""

from __future__ import annotations

import re
from typing import Any

from homecircle_feed.geo import is_iana
from homecircle_feed.schedule import DAY_NAMES
from homecircle_feed.tags import TAG_ORDER
from homecircle_feed.text import EMAIL_RE

BANNED_KEYS = {
    "edit_url",
    "author",
    "email",
    "entity_email",
    "feedback_emails",
    "admin_notes",
    "contact_email_1",
    "contact_email_2",
    "contact_name_1",
    "contact_name_2",
    "contact_phone_1",
    "contact_phone_2",
    "email_contact",
}

CLOCK_RE = re.compile(r"^\d{2}:\d{2}$")
FORMATS = {"in_person", "online", "hybrid"}
FELLOWSHIPS = {"AA", "NA"}


def validate_meetings(meetings: list[dict[str, Any]], country: str) -> None:
    seen: set[str] = set()
    errors: list[str] = []
    for meeting in meetings:
        ident = str(meeting.get("id") or "<missing id>")
        if ident in seen:
            errors.append(f"{ident}: duplicate id")
        seen.add(ident)
        errors.extend(f"{ident}: {problem}" for problem in _problems(meeting, country))
        if len(errors) > 20:
            break
    if errors:
        joined = "\n".join(errors[:20])
        raise ValueError(f"Feed failed validation:\n{joined}")


def _problems(meeting: dict[str, Any], country: str) -> list[str]:
    problems: list[str] = []
    if meeting.get("fellowship") not in FELLOWSHIPS:
        problems.append("fellowship must be AA or NA")
    if not str(meeting.get("name") or "").strip():
        problems.append("name is empty")
    schedule = meeting.get("schedule") or {}
    weekday = schedule.get("weekday")
    if weekday not in range(7) or schedule.get("day") != DAY_NAMES[weekday]:
        problems.append("weekday and day disagree")
    if not CLOCK_RE.match(str(schedule.get("start") or "")):
        problems.append("start must be HH:MM")
    if not is_iana(schedule.get("timezone")):
        problems.append("timezone is not an IANA name")
    duration = schedule.get("duration_minutes")
    if not isinstance(duration, int) or not 1 <= duration <= 12 * 60:
        problems.append("duration_minutes is out of range")
    if meeting.get("format") not in FORMATS:
        problems.append("format must be in_person, online, or hybrid")
    location = meeting.get("location") or {}
    if location.get("country") != country:
        problems.append(f"country is {location.get('country')}, expected {country}")
    lat, lng = location.get("latitude"), location.get("longitude")
    if (lat is None) ^ (lng is None):
        problems.append("latitude and longitude must both be set or both be null")
    if lat is not None and not -90 <= lat <= 90:
        problems.append("latitude out of range")
    if lng is not None and not -180 <= lng <= 180:
        problems.append("longitude out of range")
    online = meeting.get("online") or {}
    url = online.get("url")
    if url and not str(url).startswith(("http://", "https://")):
        problems.append("online url must be http(s)")
    tags = meeting.get("tags")
    if not isinstance(tags, list) or any(tag not in TAG_ORDER for tag in tags):
        problems.append("unknown tag")
    leaked = BANNED_KEYS.intersection(_keys(meeting))
    if leaked:
        problems.append(f"unexpected fields {sorted(leaked)}")
    for field in (meeting.get("notes"), meeting.get("name")):
        if field and EMAIL_RE.search(str(field)):
            problems.append("email address was not removed")
    return problems


def _keys(value: object) -> set[str]:
    found: set[str] = set()
    if isinstance(value, dict):
        for key, child in value.items():
            found.add(str(key))
            found.update(_keys(child))
    elif isinstance(value, list):
        for child in value:
            found.update(_keys(child))
    return found
