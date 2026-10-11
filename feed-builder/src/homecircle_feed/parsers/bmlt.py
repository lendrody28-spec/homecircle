"""Parse a BMLT GetSearchResults payload into normalized meetings.

The fetcher asks only for public fields. If a server still returns contact
names, emails, phones, or admin notes, they are ignored here.
"""

from __future__ import annotations

from typing import Any

from homecircle_feed.geo import (
    choose_timezone,
    country_is_default,
    normalize_country,
    normalize_state,
    postal_code,
    state_from_coordinates,
    usable_coordinates,
)
from homecircle_feed.meeting import meeting_record
from homecircle_feed.schedule import bmlt_weekday, day_name, duration_from_clock, parse_clock
from homecircle_feed.tags import BMLT_KEY_TAGS, ordered_tags, tag_from_format_name
from homecircle_feed.text import public_notes, tidy_place

VENUE_FORMATS = {1: "in_person", 2: "online", 3: "hybrid"}


class ParseResult:
    def __init__(self) -> None:
        self.meetings: list[dict[str, Any]] = []
        self.withheld: dict[str, int] = {
            "unpublished": 0,
            "outside_country": 0,
            "invalid": 0,
        }

    def as_dict(self) -> dict[str, int]:
        return dict(self.withheld)


def _format_catalog(formats: list[dict[str, Any]] | None) -> tuple[dict[str, str], dict[str, str]]:
    by_key: dict[str, str] = {}
    by_id: dict[str, str] = {}
    for item in formats or []:
        key = str(item.get("key_string") or "").strip()
        name = str(item.get("name_string") or "")
        tag = BMLT_KEY_TAGS.get(key.upper()) or BMLT_KEY_TAGS.get(key) or tag_from_format_name(name)
        if key and tag:
            by_key[key.upper()] = tag
        if item.get("id") is not None and tag:
            by_id[str(item["id"])] = tag
    for key, tag in BMLT_KEY_TAGS.items():
        by_key.setdefault(key.upper(), tag)
    return by_key, by_id


def _tags(raw_formats: object, by_key: dict[str, str], by_id: dict[str, str]) -> list[str]:
    found: set[str] = set()
    for token in str(raw_formats or "").replace(";", ",").split(","):
        token = token.strip()
        if not token:
            continue
        tag = by_id.get(token) if token.isdigit() else by_key.get(token.upper())
        if tag:
            found.add(tag)
    return ordered_tags(found)


def _http_url(value: object) -> str | None:
    text = str(value or "").strip()
    if text.lower().startswith(("http://", "https://")):
        return text
    return None


def parse_bmlt(
    meetings: list[dict[str, Any]],
    *,
    country: str,
    country_default_timezone: str,
    source_id: str,
    source_name: str,
    source_url: str,
    last_seen: str,
    formats: list[dict[str, Any]] | None = None,
) -> ParseResult:
    result = ParseResult()
    by_key, by_id = _format_catalog(formats)
    seen: set[str] = set()
    for row in meetings:
        if str(row.get("published", "1")).strip() in {"0", "false", "False"}:
            result.withheld["unpublished"] += 1
            continue
        if not country_is_default(row.get("location_nation"), country):
            result.withheld["outside_country"] += 1
            continue
        weekday = bmlt_weekday(row.get("weekday_tinyint"))
        start = parse_clock(row.get("start_time"))
        name = _meeting_name(row.get("meeting_name"))
        record_id = str(row.get("id_bigint") or "").strip()
        if weekday is None or start is None or not name or not record_id:
            result.withheld["invalid"] += 1
            continue
        lat, lng = usable_coordinates(row.get("latitude"), row.get("longitude"))
        state = normalize_state(row.get("location_province")) or state_from_coordinates(lat, lng)
        timezone, timezone_source = choose_timezone(
            row.get("time_zone"),
            state,
            country_default_timezone,
        )
        try:
            venue = int(str(row.get("venue_type") or "1"))
        except ValueError:
            venue = 1
        meeting_format = VENUE_FORMATS.get(venue, "in_person")
        url = _http_url(row.get("virtual_meeting_link"))
        phone = str(row.get("phone_meeting_number") or "").strip() or None
        if meeting_format == "in_person" and (url or phone):
            meeting_format = "hybrid"
        meeting_id = f"na:{country.lower()}:{record_id}"
        if meeting_id in seen:
            result.withheld["invalid"] += 1
            continue
        seen.add(meeting_id)
        nation = normalize_country(row.get("location_nation"), default=country)
        result.meetings.append(
            meeting_record(
                id=meeting_id,
                fellowship="NA",
                name=name,
                weekday=weekday,
                day=day_name(weekday),
                start=start,
                timezone=timezone,
                timezone_source=timezone_source,
                duration_minutes=duration_from_clock(row.get("duration_time")),
                format=meeting_format,
                location_name=tidy_place(row.get("location_text")),
                address=_street(row.get("location_street")),
                suburb=tidy_place(row.get("location_municipality")),
                state=state,
                postal_code=postal_code(row.get("location_postal_code_1")),
                country=nation,
                latitude=lat,
                longitude=lng,
                approximate=False,
                online_url=url,
                online_phone=phone,
                tags=_tags(row.get("formats"), by_key, by_id),
                notes=public_notes(
                    row.get("comments"),
                    row.get("virtual_meeting_additional_info"),
                    row.get("location_info"),
                ),
                source_id=source_id,
                source_name=source_name,
                source_url=source_url,
                record_url=None,
                last_seen=last_seen,
            )
        )
    return result


def _meeting_name(value: object) -> str | None:
    from homecircle_feed.text import clean_text

    text = clean_text(value)
    if not text:
        return None
    if len(text) > 200:
        return text[:199].rstrip() + "…"
    return text


def _street(value: object) -> str | None:
    text = str(value or "").strip()
    if not text:
        return None
    from homecircle_feed.text import clean_text

    return clean_text(text)
