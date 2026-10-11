"""Parse a Meeting Guide / TSML JSON feed into normalized meetings.

Admin fields (edit URLs, author logins, group emails, feedback addresses, and
personal phone numbers) are not copied. Conference URL and dial-in are kept
because they are how someone attends.
"""

from __future__ import annotations

from typing import Any

from homecircle_feed.geo import (
    choose_timezone,
    normalize_state,
    parse_au_address,
    state_from_coordinates,
    usable_coordinates,
)
from homecircle_feed.meeting import meeting_record
from homecircle_feed.schedule import day_name, duration_between, parse_clock, tsml_weekday
from homecircle_feed.tags import TSML_CODE_TAGS, ordered_tags
from homecircle_feed.text import public_notes, tidy_place

ATTENDANCE_FORMATS = {
    "in_person": "in_person",
    "online": "online",
    "hybrid": "hybrid",
}


class ParseResult:
    def __init__(self) -> None:
        self.meetings: list[dict[str, Any]] = []
        self.withheld: dict[str, int] = {
            "inactive": 0,
            "temporarily_closed": 0,
            "invalid": 0,
        }


def _tags(types: object) -> list[str]:
    found: set[str] = set()
    values = types if isinstance(types, list) else []
    for code in values:
        tag = TSML_CODE_TAGS.get(str(code).strip())
        if tag:
            found.add(tag)
    return ordered_tags(found)


def _http_url(value: object) -> str | None:
    text = str(value or "").strip()
    if text.lower().startswith(("http://", "https://")):
        return text
    return None


def _record_url(value: object) -> str | None:
    url = _http_url(value)
    if not url:
        return None
    if "/wp-admin/" in url:
        return None
    return url


def parse_tsml(
    meetings: list[dict[str, Any]],
    *,
    country: str,
    country_default_timezone: str,
    site_timezone: str | None,
    source_id: str,
    source_name: str,
    source_url: str,
    last_seen: str,
) -> ParseResult:
    result = ParseResult()
    seen: set[str] = set()
    for row in meetings:
        types = [str(code) for code in (row.get("types") or [])]
        attendance = str(row.get("attendance_option") or "").strip().lower()
        if attendance == "inactive":
            result.withheld["inactive"] += 1
            continue
        if "TC" in types:
            result.withheld["temporarily_closed"] += 1
            continue
        weekday = tsml_weekday(row.get("day"))
        start = parse_clock(row.get("time"))
        name = str(row.get("name") or "").strip() or None
        record_id = str(row.get("id") or row.get("slug") or "").strip()
        if weekday is None or start is None or not name or not record_id:
            result.withheld["invalid"] += 1
            continue
        lat, lng = usable_coordinates(row.get("latitude"), row.get("longitude"))
        state = normalize_state(row.get("region")) or normalize_state(row.get("state")) or state_from_coordinates(lat, lng)
        timezone, timezone_source = choose_timezone(
            row.get("timezone"),
            state,
            country_default_timezone,
            site_timezone=site_timezone,
        )
        meeting_format = ATTENDANCE_FORMATS.get(attendance)
        url = _http_url(row.get("conference_url"))
        phone = str(row.get("conference_phone") or "").strip() or None
        if meeting_format is None:
            if url or phone:
                meeting_format = "online"
            else:
                meeting_format = "in_person"
        address = parse_au_address(row.get("formatted_address"))
        meeting_id = f"aa:{country.lower()}:{record_id}"
        if meeting_id in seen:
            result.withheld["invalid"] += 1
            continue
        seen.add(meeting_id)
        approximate = str(row.get("approximate") or "").strip().lower() in {"yes", "true", "1"}
        result.meetings.append(
            meeting_record(
                id=meeting_id,
                fellowship="AA",
                name=name,
                weekday=weekday,
                day=day_name(weekday),
                start=start,
                timezone=timezone,
                timezone_source=timezone_source,
                duration_minutes=duration_between(start, row.get("end_time")),
                format=meeting_format,
                location_name=tidy_place(row.get("location")),
                address=address["address"],
                suburb=address["suburb"],
                state=state,
                postal_code=address["postal_code"],
                country=country,
                latitude=lat,
                longitude=lng,
                approximate=approximate,
                online_url=url,
                online_phone=phone,
                tags=_tags(types),
                notes=public_notes(row.get("notes"), row.get("conference_url_notes"), row.get("conference_phone_notes")),
                source_id=source_id,
                source_name=source_name,
                source_url=source_url,
                record_url=_record_url(row.get("url")),
                last_seen=last_seen,
            )
        )
    return result
