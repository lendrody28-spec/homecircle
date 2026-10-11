"""Rebuild the previous full snapshot from the files already published on the site.

The nightly job runs on a fresh GitHub Actions checkout, so dist/<cc>/meetings.json
from the last run is not on disk. The published shards (index.json, the state files
and online.json) hold every meeting; only each meeting's source name and url were
moved onto the file wrapper. This puts them back so the pipeline can diff against
yesterday, carry a failed source, and apply the low-count guard.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from homecircle_feed.pipeline import load_json, write_json


def snapshot_from_published(feed_dir: Path) -> dict[str, Any] | None:
    index_path = feed_dir / "index.json"
    if not index_path.exists():
        return None
    index = load_json(index_path)
    catalog = {item["id"]: item for item in index.get("sources") or []}
    merged: dict[str, dict[str, Any]] = {}
    for entry in index.get("states") or []:
        path = feed_dir / entry["file"]
        if not path.exists():
            raise FileNotFoundError(f"{path} is listed in index.json but missing")
        body = load_json(path)
        for source in body.get("sources") or []:
            catalog.setdefault(source["id"], source)
        for row in body.get("meetings") or []:
            source = dict(row.get("source") or {})
            known = catalog.get(source.get("id"), {})
            meeting = dict(row)
            meeting["source"] = {
                "id": source.get("id"),
                "name": known.get("name"),
                "url": known.get("url"),
                "record_url": source.get("record_url"),
                "last_seen": source.get("last_seen"),
            }
            merged[meeting["id"]] = meeting
    meetings = list(merged.values())
    return {
        "schema_version": index.get("schema_version"),
        "country": index.get("country"),
        "generated_at": index.get("generated_at"),
        "meeting_count": len(meetings),
        "sources": [],
        "meetings": meetings,
    }


def seed_previous(feed_dir: Path, output_dir: Path, *, force: bool = False) -> dict[str, Any]:
    snapshot = snapshot_from_published(feed_dir)
    if snapshot is None:
        return {"seeded": False, "reason": f"no index.json in {feed_dir}"}
    target = output_dir / str(snapshot["country"]).lower() / "meetings.json"
    if target.exists() and not force:
        return {"seeded": False, "reason": f"{target} already exists"}
    write_json(target, snapshot, pretty=False)
    return {
        "seeded": True,
        "path": str(target),
        "meeting_count": snapshot["meeting_count"],
        "generated_at": snapshot["generated_at"],
    }
