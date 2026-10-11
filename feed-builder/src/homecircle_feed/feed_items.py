"""Curated news and events. Nothing is published unless a person set approved=true."""

from __future__ import annotations

from typing import Any

from homecircle_feed import SCHEMA_VERSION

REQUIRED = ("id", "publisher", "title", "url", "approved")
PUBLIC_FIELDS = (
    "id",
    "publisher",
    "kind",
    "title",
    "summary",
    "url",
    "starts_at",
    "ends_at",
    "approved",
)


class FeedItemError(ValueError):
    pass


def publish_feed_items(items: list[dict[str, Any]], generated_at: str) -> tuple[dict[str, Any], int]:
    published: list[dict[str, Any]] = []
    withheld = 0
    seen: set[str] = set()
    for item in items:
        ident = str(item.get("id") or "<missing id>")
        missing = [field for field in REQUIRED if field not in item]
        if missing:
            raise FeedItemError(f"{ident} is missing {', '.join(missing)}")
        if not isinstance(item["approved"], bool):
            raise FeedItemError(f"{ident} approved must be true or false, not {item['approved']!r}")
        if ident in seen:
            raise FeedItemError(f"duplicate feed item id {ident}")
        seen.add(ident)
        if not item["approved"]:
            withheld += 1
            continue
        url = str(item.get("url") or "")
        if not url.startswith(("http://", "https://")):
            raise FeedItemError(f"{ident} has no public http(s) url")
        published.append({field: item.get(field) for field in PUBLIC_FIELDS})
    payload = {
        "schema_version": SCHEMA_VERSION,
        "generated_at": generated_at,
        "item_count": len(published),
        "withheld_unapproved": withheld,
        "items": published,
    }
    return payload, withheld
