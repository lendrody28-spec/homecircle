"""Build per-country meeting files, a changes report, and the curated feed."""

from __future__ import annotations

import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable
from urllib.parse import urlencode
from zoneinfo import ZoneInfo

from homecircle_feed import SCHEMA_VERSION
from homecircle_feed.changes import meeting_changes
from homecircle_feed.feed_items import publish_feed_items
from homecircle_feed.http_client import FetchError
from homecircle_feed.links import broken_meetings, check_links, summarize
from homecircle_feed.parsers.bmlt import parse_bmlt
from homecircle_feed.parsers.tsml import parse_tsml
from homecircle_feed.split import write_state_feed
from homecircle_feed.validate import validate_meetings

BRISBANE = ZoneInfo("Australia/Brisbane")
BMLT_FIELDS = ",".join(
    [
        "id_bigint",
        "meeting_name",
        "weekday_tinyint",
        "start_time",
        "duration_time",
        "time_zone",
        "venue_type",
        "formats",
        "latitude",
        "longitude",
        "location_text",
        "location_street",
        "location_info",
        "location_municipality",
        "location_province",
        "location_postal_code_1",
        "location_nation",
        "comments",
        "virtual_meeting_link",
        "virtual_meeting_additional_info",
        "phone_meeting_number",
        "published",
    ]
)


# A source that returns fewer than min_keep_ratio of its previous meeting count
# keeps its previous rows. Sources with fewer than min_previous rows last time
# are not guarded (small lists can legitimately swing a lot).
DEFAULT_GUARD = {"min_keep_ratio": 0.5, "min_previous": 20}


def _too_few(current: int, previous: int, guard: dict[str, Any]) -> bool:
    if previous < int(guard.get("min_previous", 0)):
        return False
    return current < previous * float(guard.get("min_keep_ratio", 0))


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload: Any, pretty: bool = False) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if pretty:
        text = json.dumps(payload, indent=2, ensure_ascii=False) + "\n"
    else:
        text = json.dumps(payload, ensure_ascii=False, separators=(",", ":")) + "\n"
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(text, encoding="utf-8")
    temporary.replace(path)


def bmlt_url(root: str, switcher: str, **params: str) -> str:
    base = root.rstrip("/") + "/"
    query = urlencode({"switcher": switcher, **params})
    return f"{base}client_interface/json/?{query}"


def build(
    *,
    registry_path: Path,
    curated_path: Path,
    output_dir: Path,
    get_json: Callable[[str], Any],
    countries: list[str] | None = None,
    check_link_urls: bool = True,
    link_cache: Path | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    moment = now or datetime.now(timezone.utc)
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)
    generated_at = moment.astimezone(timezone.utc).isoformat()
    report_day = moment.astimezone(BRISBANE).date().isoformat()
    registry = load_json(registry_path)
    selected = {code.upper() for code in countries} if countries else None
    summaries = []
    for country in registry["countries"]:
        if not country.get("enabled", False):
            continue
        if selected and country["code"].upper() not in selected:
            continue
        summaries.append(
            _build_country(
                country,
                output_dir=output_dir,
                get_json=get_json,
                generated_at=generated_at,
                report_day=report_day,
                check_link_urls=check_link_urls,
                link_cache=link_cache,
                not_used=registry.get("not_used") or [],
            )
        )
    curated_payload = load_json(curated_path) if curated_path.exists() else []
    if isinstance(curated_payload, dict):
        curated = list(curated_payload.get("items") or [])
    else:
        curated = list(curated_payload)
    feed_items, withheld = publish_feed_items(curated, generated_at)
    write_json(output_dir / "feed-items.json", feed_items, pretty=True)
    index = {
        "schema_version": SCHEMA_VERSION,
        "generated_at": generated_at,
        "schedule": registry.get("schedule"),
        "feeds": [
            {
                "country": item["country"],
                "path": f"feed/{item['country'].lower()}/index.json",
                "meeting_count": item["meeting_count"],
            }
            for item in summaries
        ],
        "feed_items": "feed-items.json",
        "feed_items_published": feed_items["item_count"],
        "feed_items_withheld_unapproved": withheld,
    }
    write_json(output_dir / "index.json", index, pretty=True)
    return {"countries": summaries, "feed_items": feed_items, "index": index}


def _build_country(
    country: dict[str, Any],
    *,
    output_dir: Path,
    get_json: Callable[[str], Any],
    generated_at: str,
    report_day: str,
    check_link_urls: bool,
    link_cache: Path | None,
    not_used: list[dict[str, Any]],
) -> dict[str, Any]:
    code = country["code"].upper()
    folder = output_dir / code.lower()
    previous_path = folder / "meetings.json"
    previous = _previous_meetings(previous_path)
    previous_counts = Counter(meeting["source"]["id"] for meeting in previous)
    guard = {**DEFAULT_GUARD, **(country.get("guard") or {})}
    fresh: list[dict[str, Any]] = []
    failed_sources: set[str] = set()
    source_reports = []
    for source in country.get("sources") or []:
        if not source.get("enabled", True):
            source_reports.append(
                {
                    "id": source["id"],
                    "name": source.get("name"),
                    "status": "disabled",
                    "fetched": 0,
                    "kept": 0,
                    "withheld": {},
                    "error": source.get("notes"),
                }
            )
            continue
        try:
            parsed, fetched = _fetch_source(source, country, get_json, generated_at)
        except Exception as error:
            failed_sources.add(source["id"])
            source_reports.append(
                {
                    "id": source["id"],
                    "name": source.get("name"),
                    "status": "error",
                    "fetched": 0,
                    "kept": 0,
                    "withheld": {},
                    "error": str(error)[:300],
                }
            )
            continue
        previous_count = previous_counts.get(source["id"], 0)
        if _too_few(len(parsed.meetings), previous_count, guard):
            # Safety guard: a source that suddenly returns far fewer meetings
            # than last time is treated like a failed fetch, so yesterday's
            # rows for that source are kept instead of being wiped.
            failed_sources.add(source["id"])
            message = (
                f"returned {len(parsed.meetings)} meetings, previous build had {previous_count}; "
                f"below {guard['min_keep_ratio']:.0%} so the previous rows were kept"
            )
            print(f"guard {source['id']}: {message}", flush=True)
            source_reports.append(
                {
                    "id": source["id"],
                    "name": source.get("name"),
                    "status": "kept_previous",
                    "fetched": fetched,
                    "kept": 0,
                    "withheld": parsed.withheld,
                    "error": message,
                }
            )
            continue
        fresh.extend(parsed.meetings)
        source_reports.append(
            {
                "id": source["id"],
                "name": source.get("name"),
                "status": "ok",
                "fetched": fetched,
                "kept": len(parsed.meetings),
                "withheld": parsed.withheld,
                "error": None,
            }
        )
    carried = [meeting for meeting in previous if meeting["source"]["id"] in failed_sources]
    merged = {meeting["id"]: meeting for meeting in carried}
    for meeting in fresh:
        merged[meeting["id"]] = meeting
    meetings = sorted(merged.values(), key=_sort_key)
    validate_meetings(meetings, code)
    # Diff only the sources that refreshed. Carried rows are unchanged on purpose.
    compared_ids = {source["id"] for source in source_reports if source["status"] not in ("error", "kept_previous")}
    previous_refreshed = [meeting for meeting in previous if meeting["source"]["id"] in compared_ids]
    current_refreshed = [meeting for meeting in meetings if meeting["source"]["id"] in compared_ids]
    delta = meeting_changes(previous_refreshed, current_refreshed)
    link_summary = {"ok": 0, "broken": 0, "blocked_by_host": 0, "skipped": True}
    broken: list[dict[str, Any]] = []
    if check_link_urls:
        urls = [meeting["online"]["url"] for meeting in meetings if meeting["online"]["url"]]
        statuses = check_links(urls, cache_path=link_cache)
        broken = broken_meetings(meetings, statuses)
        link_summary = {**summarize(statuses), "skipped": False}
    payload = {
        "schema_version": SCHEMA_VERSION,
        "country": code,
        "country_name": country["name"],
        "generated_at": generated_at,
        "meeting_count": len(meetings),
        "sources": source_reports,
        "meetings": meetings,
    }
    write_json(folder / "meetings.json", payload, pretty=True)
    publish_paths = write_state_feed(payload, output_dir / "feed" / code.lower())
    coverage = _coverage(code, meetings, source_reports, not_used, generated_at, link_summary)
    write_json(folder / "coverage.json", coverage, pretty=True)
    changes = {
        "schema_version": SCHEMA_VERSION,
        "country": code,
        "generated_at": generated_at,
        "report_day": report_day,
        "previous_count": len(previous),
        "current_count": len(meetings),
        "added_count": len(delta["added"]),
        "removed_count": len(delta["removed"]),
        "changed_count": len(delta["changed"]),
        "broken_link_count": len(broken),
        "link_check": link_summary,
        "stale_sources": sorted(failed_sources),
        "added": delta["added"],
        "removed": delta["removed"],
        "changed": delta["changed"],
        "broken_links": broken,
    }
    changes_dir = output_dir / "changes" / code.lower()
    write_json(changes_dir / "latest.json", changes, pretty=True)
    write_json(changes_dir / f"{report_day}.json", changes, pretty=True)
    return {
        "country": code,
        "meeting_count": len(meetings),
        "added": len(delta["added"]),
        "removed": len(delta["removed"]),
        "changed": len(delta["changed"]),
        "broken_links": len(broken),
        "sources": source_reports,
        "coverage": coverage,
        "publish_files": [str(path) for path in publish_paths],
    }


def _fetch_source(source: dict[str, Any], country: dict[str, Any], get_json: Callable[[str], Any], last_seen: str):
    kind = source["kind"]
    print(f"fetch {source['id']}", flush=True)
    if kind == "bmlt":
        root = source["root_url"]
        formats_payload = []
        try:
            loaded = get_json(bmlt_url(root, "GetFormats"))
            if isinstance(loaded, list):
                formats_payload = loaded
        except FetchError:
            formats_payload = []
        payload = get_json(bmlt_url(root, "GetSearchResults", data_field_key=BMLT_FIELDS))
        if not isinstance(payload, list):
            raise ValueError(f"{source['id']} did not return a JSON array")
        parsed = parse_bmlt(
            payload,
            country=country["code"],
            country_default_timezone=country["default_timezone"],
            source_id=source["id"],
            source_name=source["name"],
            source_url=root,
            last_seen=last_seen,
            formats=formats_payload,
        )
        return parsed, len(payload)
    if kind == "tsml":
        payload = get_json(source["feed_url"])
        if not isinstance(payload, list):
            raise ValueError(f"{source['id']} did not return a JSON array")
        parsed = parse_tsml(
            payload,
            country=country["code"],
            country_default_timezone=country["default_timezone"],
            site_timezone=source.get("site_timezone"),
            source_id=source["id"],
            source_name=source["name"],
            source_url=source["feed_url"],
            last_seen=last_seen,
        )
        return parsed, len(payload)
    raise ValueError(f"Unknown source kind {kind}")


def _previous_meetings(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    payload = load_json(path)
    meetings = payload.get("meetings") if isinstance(payload, dict) else None
    return list(meetings or [])


def _sort_key(meeting: dict[str, Any]) -> tuple:
    state = meeting["location"].get("state") or "ZZZ"
    schedule = meeting["schedule"]
    return (state, schedule["weekday"], schedule["start"], meeting["name"].casefold(), meeting["id"])


def _coverage(
    country: str,
    meetings: list[dict[str, Any]],
    source_reports: list[dict[str, Any]],
    not_used: list[dict[str, Any]],
    generated_at: str,
    link_summary: dict[str, Any],
) -> dict[str, Any]:
    by_fellowship: Counter[str] = Counter()
    by_format: Counter[str] = Counter()
    by_state: Counter[str] = Counter()
    by_tag: Counter[str] = Counter()
    by_timezone_source: Counter[str] = Counter()
    with_coordinates = 0
    with_url = 0
    with_phone = 0
    for meeting in meetings:
        by_fellowship[meeting["fellowship"]] += 1
        by_format[meeting["format"]] += 1
        by_state[meeting["location"].get("state") or "unknown"] += 1
        by_timezone_source[meeting["schedule"]["timezone_source"]] += 1
        if meeting["location"]["latitude"] is not None:
            with_coordinates += 1
        if meeting["online"]["url"]:
            with_url += 1
        if meeting["online"]["phone"]:
            with_phone += 1
        for tag in meeting["tags"]:
            by_tag[tag] += 1
    withheld: Counter[str] = Counter()
    for report in source_reports:
        for reason, count in (report.get("withheld") or {}).items():
            withheld[reason] += count
    return {
        "schema_version": SCHEMA_VERSION,
        "country": country,
        "generated_at": generated_at,
        "meeting_count": len(meetings),
        "by_fellowship": dict(sorted(by_fellowship.items())),
        "by_format": dict(sorted(by_format.items())),
        "by_state": dict(sorted(by_state.items())),
        "by_tag": dict(sorted(by_tag.items())),
        "by_timezone_source": dict(sorted(by_timezone_source.items())),
        "with_coordinates": with_coordinates,
        "with_online_url": with_url,
        "with_online_phone": with_phone,
        "withheld": dict(sorted(withheld.items())),
        "sources": source_reports,
        "not_used": not_used,
        "link_check": link_summary,
    }
