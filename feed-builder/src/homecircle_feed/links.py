"""Polite checks for meeting join URLs.

Zoom and similar hosts often refuse HEAD or return 403 to unknown clients.
Those responses mean the host is there, not that the meeting was removed.
404, 410, and 5xx, plus DNS and connection failures, count as broken.
"""

from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

OK = "ok"
BROKEN = "broken"
BLOCKED = "blocked_by_host"


@dataclass
class LinkStatus:
    url: str
    status: str
    reason: str

    def as_dict(self) -> dict[str, str]:
        return {"url": self.url, "status": self.status, "reason": self.reason}


def classify_http(code: int) -> LinkStatus | None:
    """Return a status for an HTTP code, or None when the caller should try GET."""
    if 200 <= code < 400:
        return LinkStatus("", OK, f"http_{code}")
    if code in {401, 403, 429}:
        return LinkStatus("", BLOCKED, f"http_{code}")
    if code == 405:
        return None
    if code in {404, 410} or code >= 500 or 400 <= code < 500:
        return LinkStatus("", BROKEN, f"http_{code}")
    return LinkStatus("", BROKEN, f"http_{code}")


def check_url(url: str, opener: Callable[..., Any], timeout: float = 8) -> LinkStatus:
    for method in ("HEAD", "GET"):
        request = Request(url, method=method, headers={"User-Agent": "HomeCircleMeetingFeed/1.0"})
        try:
            with opener(request, timeout=timeout) as response:
                code = getattr(response, "status", None) or response.getcode()
                classified = classify_http(int(code))
                if classified is None:
                    continue
                classified.url = url
                return classified
        except HTTPError as error:
            classified = classify_http(int(error.code))
            if classified is None:
                continue
            classified.url = url
            return classified
        except URLError as error:
            return LinkStatus(url, BROKEN, f"unreachable:{error.reason}")
        except TimeoutError:
            return LinkStatus(url, BROKEN, "timeout")
        except OSError as error:
            return LinkStatus(url, BROKEN, f"unreachable:{error}")
    return LinkStatus(url, BROKEN, "no_response")


def check_links(
    urls: list[str],
    *,
    cache_path: Path | None = None,
    cache_hours: float = 18,
    workers: int = 6,
    timeout: float = 8,
    opener: Callable[..., Any] | None = None,
    now: datetime | None = None,
) -> dict[str, LinkStatus]:
    moment = now or datetime.now(timezone.utc)
    unique = sorted({url for url in urls if url})
    cached = _read_cache(cache_path, moment, cache_hours) if cache_path else {}
    pending = [url for url in unique if url not in cached]
    results = dict(cached)
    fetch = opener or urlopen
    if pending:
        with ThreadPoolExecutor(max_workers=workers) as pool:
            futures = {pool.submit(check_url, url, fetch, timeout): url for url in pending}
            done = 0
            for future in as_completed(futures):
                status = future.result()
                results[status.url] = status
                done += 1
                if done % 50 == 0:
                    print(f"checked {done}/{len(pending)} join links", flush=True)
    if cache_path:
        _write_cache(cache_path, results, moment)
    return results


def broken_meetings(meetings: list[dict[str, Any]], statuses: dict[str, LinkStatus]) -> list[dict[str, Any]]:
    broken = []
    for meeting in meetings:
        url = (meeting.get("online") or {}).get("url")
        status = statuses.get(url or "")
        if status and status.status == BROKEN:
            broken.append(
                {
                    "id": meeting["id"],
                    "name": meeting.get("name"),
                    "fellowship": meeting.get("fellowship"),
                    "url": url,
                    "reason": status.reason,
                }
            )
    broken.sort(key=lambda item: item["id"])
    return broken


def summarize(statuses: dict[str, LinkStatus]) -> dict[str, int]:
    summary = {OK: 0, BROKEN: 0, BLOCKED: 0}
    for status in statuses.values():
        summary[status.status] = summary.get(status.status, 0) + 1
    return summary


def _read_cache(path: Path, now: datetime, cache_hours: float) -> dict[str, LinkStatus]:
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    checked = datetime.fromisoformat(payload.get("checked_at"))
    if checked.tzinfo is None:
        checked = checked.replace(tzinfo=timezone.utc)
    if now - checked > timedelta(hours=cache_hours):
        return {}
    loaded = {}
    for url, item in (payload.get("results") or {}).items():
        loaded[url] = LinkStatus(url, item["status"], item["reason"])
    return loaded


def _write_cache(path: Path, results: dict[str, LinkStatus], now: datetime) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "checked_at": now.isoformat(),
        "results": {url: status.as_dict() for url, status in results.items()},
    }
    path.write_text(json.dumps(payload), encoding="utf-8")
