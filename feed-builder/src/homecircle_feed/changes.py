"""Added, removed, and changed meetings between two feeds."""

from __future__ import annotations

from typing import Any

from homecircle_feed.meeting import comparable


def _index(meetings: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    return {meeting["id"]: meeting for meeting in meetings}


def meeting_changes(
    previous: list[dict[str, Any]],
    current: list[dict[str, Any]],
) -> dict[str, Any]:
    old = _index(previous)
    new = _index(current)
    added = [_brief(new[key]) for key in sorted(new) if key not in old]
    removed = [_brief(old[key]) for key in sorted(old) if key not in new]
    changed = []
    for key in sorted(set(old) & set(new)):
        if comparable(old[key]) != comparable(new[key]):
            fields = _changed_fields(old[key], new[key])
            changed.append({**_brief(new[key]), "fields": fields})
    return {"added": added, "removed": removed, "changed": changed}


def _brief(meeting: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": meeting["id"],
        "fellowship": meeting.get("fellowship"),
        "name": meeting.get("name"),
        "format": meeting.get("format"),
        "state": (meeting.get("location") or {}).get("state"),
    }


def _changed_fields(before: dict[str, Any], after: dict[str, Any]) -> list[str]:
    fields: list[str] = []
    for key in ("name", "fellowship", "format", "tags", "notes"):
        if before.get(key) != after.get(key):
            fields.append(key)
    if before.get("schedule") != after.get("schedule"):
        fields.append("schedule")
    if before.get("location") != after.get("location"):
        fields.append("location")
    if before.get("online") != after.get("online"):
        fields.append("online")
    return fields
