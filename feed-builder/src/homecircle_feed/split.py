"""Split a country feed into minified per-state files for static hosting.

Each published file stays under 900 KB. Online meetings are listed in their
state file and again in online.json. Rows with no state go in unknown.json.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

PUBLISH_MAX_BYTES = 900_000
STATE_ORDER = ("NSW", "VIC", "QLD", "WA", "SA", "TAS", "ACT", "NT")


def minify(payload: dict[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False, separators=(",", ":"))


def publish_meeting(meeting: dict[str, Any]) -> dict[str, Any]:
    """Drop source name and URL. Those live on the file wrapper."""
    source = meeting["source"]
    row = dict(meeting)
    row["source"] = {
        "id": source["id"],
        "record_url": source.get("record_url"),
        "last_seen": source["last_seen"],
    }
    return row


def source_catalog(meetings: list[dict[str, Any]]) -> list[dict[str, str]]:
    catalog: list[dict[str, str]] = []
    seen: set[str] = set()
    for meeting in meetings:
        source = meeting["source"]
        if source["id"] in seen:
            continue
        seen.add(source["id"])
        catalog.append({"id": source["id"], "name": source["name"], "url": source["url"]})
    return catalog


def split_country(
    payload: dict[str, Any],
    *,
    max_bytes: int = PUBLISH_MAX_BYTES,
) -> dict[str, Any]:
    """Return index plus {filename: payload} for one country."""
    meetings = list(payload["meetings"])
    catalog = source_catalog(meetings)
    by_state: dict[str, list[dict[str, Any]]] = {state: [] for state in STATE_ORDER}
    unknown: list[dict[str, Any]] = []
    online: list[dict[str, Any]] = []
    for meeting in meetings:
        row = publish_meeting(meeting)
        state = (meeting.get("location") or {}).get("state")
        if state in by_state:
            by_state[state].append(row)
        else:
            unknown.append(row)
        if meeting.get("format") == "online":
            online.append(row)
    header = {
        "schema_version": payload["schema_version"],
        "country": payload["country"],
        "generated_at": payload["generated_at"],
    }
    files: dict[str, dict[str, Any]] = {}
    states: list[dict[str, Any]] = []
    buckets: list[tuple[str, list[dict[str, Any]]]] = [(state, by_state[state]) for state in STATE_ORDER]
    buckets.append(("online", online))
    buckets.append(("unknown", unknown))
    for name, rows in buckets:
        if not rows:
            continue
        parts = _pack(name, rows, header=header, catalog=catalog, max_bytes=max_bytes)
        for filename, body in parts:
            files[filename] = body
            states.append({"state": name, "file": filename, "meeting_count": body["meeting_count"]})
    index = {
        **header,
        "meeting_count": len(meetings),
        "sources": catalog,
        "states": states,
    }
    return {"index": index, "files": files}


def write_state_feed(payload: dict[str, Any], directory: Path, *, max_bytes: int = PUBLISH_MAX_BYTES) -> list[Path]:
    """Write index.json and the state shards. Removes stale JSON in that directory."""
    packed = split_country(payload, max_bytes=max_bytes)
    directory.mkdir(parents=True, exist_ok=True)
    written = {"index.json"}
    written.update(packed["files"])
    for stale in directory.glob("*.json"):
        if stale.name not in written:
            stale.unlink()
    paths = [_write_minified(directory / "index.json", packed["index"])]
    for filename, body in packed["files"].items():
        paths.append(_write_minified(directory / filename, body))
    return paths


def _pack(
    name: str,
    rows: list[dict[str, Any]],
    *,
    header: dict[str, Any],
    catalog: list[dict[str, str]],
    max_bytes: int,
) -> list[tuple[str, dict[str, Any]]]:
    single = _file_body(rows, header=header, catalog=catalog)
    if _size(single) <= max_bytes:
        return [(f"{name}.json", single)]
    parts: list[list[dict[str, Any]]] = []
    current: list[dict[str, Any]] = []
    for row in rows:
        trial = current + [row]
        if current and _size(_file_body(trial, header=header, catalog=catalog)) > max_bytes:
            parts.append(current)
            current = [row]
        else:
            current = trial
    if current:
        parts.append(current)
    named: list[tuple[str, dict[str, Any]]] = []
    for index, part in enumerate(parts, start=1):
        body = _file_body(part, header=header, catalog=catalog)
        if _size(body) > max_bytes:
            raise ValueError(f"{name} part {index} is {_size(body)} bytes, over the {max_bytes} byte publish limit")
        named.append((f"{name}-{index}.json", body))
    return named


def _file_body(
    rows: list[dict[str, Any]],
    *,
    header: dict[str, Any],
    catalog: list[dict[str, str]],
) -> dict[str, Any]:
    ids: list[str] = []
    seen: set[str] = set()
    for row in rows:
        source_id = row["source"]["id"]
        if source_id not in seen:
            seen.add(source_id)
            ids.append(source_id)
    by_id = {item["id"]: item for item in catalog}
    return {
        **header,
        "meeting_count": len(rows),
        "sources": [by_id[source_id] for source_id in ids],
        "meetings": rows,
    }


def _size(payload: dict[str, Any]) -> int:
    return len(minify(payload).encode("utf-8"))


def _write_minified(path: Path, payload: dict[str, Any]) -> Path:
    path.write_text(minify(payload), encoding="utf-8")
    return path
