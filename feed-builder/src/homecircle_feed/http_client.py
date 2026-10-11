"""Polite HTTP fetch: robots.txt, a per-host delay, and a disk cache."""

from __future__ import annotations

import hashlib
import json
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen

MAX_BYTES = 40_000_000
CACHE_HOURS = 12
MAX_CRAWL_DELAY = 10.0


class FetchError(Exception):
    pass


class RobotsDenied(FetchError):
    pass


class RobotsPolicy:
    """Longest-match robots.txt check.

    Python's urllib parser returns the first matching rule, so an Allow for
    /wp-admin/admin-ajax.php loses to Disallow: /wp-admin/. RFC 9309 uses the
    longest path. An equal-length tie allows the fetch.
    """

    def __init__(self) -> None:
        self.groups: list[dict] = []

    def allowed(self, url: str, user_agent: str) -> bool:
        group = self._group(user_agent)
        if group is None:
            return True
        path = urlparse(url).path or "/"
        best_length = -1
        best_allow = True
        for allow, rule_path in group["rules"]:
            if rule_path and path.startswith(rule_path) and len(rule_path) >= best_length:
                if len(rule_path) > best_length or allow:
                    best_length = len(rule_path)
                    best_allow = allow
        return best_allow

    def crawl_delay(self, user_agent: str) -> float | None:
        group = self._group(user_agent)
        if not group:
            return None
        return group["delay"]

    def _group(self, user_agent: str) -> dict | None:
        agent = user_agent.lower()
        specific = None
        specific_length = -1
        fallback = None
        for group in self.groups:
            for name in group["agents"]:
                if name == "*":
                    fallback = group
                elif name in agent and len(name) > specific_length:
                    specific = group
                    specific_length = len(name)
        return specific or fallback


def parse_robots(robots_text: str) -> RobotsPolicy:
    policy = RobotsPolicy()
    agents: list[str] = []
    rules: list[tuple[bool, str]] = []
    delay: float | None = None

    def flush() -> None:
        nonlocal agents, rules, delay
        if agents:
            policy.groups.append({"agents": agents, "rules": rules, "delay": delay})
        agents, rules, delay = [], [], None

    for raw in robots_text.splitlines():
        line = raw.split("#", 1)[0].strip()
        if not line or ":" not in line:
            continue
        key, value = (part.strip() for part in line.split(":", 1))
        key = key.lower()
        if key == "user-agent":
            if rules or delay is not None:
                flush()
            agents.append(value.lower())
        elif key == "disallow" and agents:
            rules.append((False, value))
        elif key == "allow" and agents:
            rules.append((True, value))
        elif key == "crawl-delay" and agents:
            try:
                delay = float(value)
            except ValueError:
                continue
    flush()
    return policy


def allowed_by_robots(robots_text: str, url: str, user_agent: str) -> bool:
    return parse_robots(robots_text).allowed(url, user_agent)


class PoliteClient:
    def __init__(
        self,
        cache_dir: Path,
        user_agent: str,
        min_interval: float = 1.0,
        timeout: float = 90,
    ) -> None:
        self.cache_dir = cache_dir
        self.user_agent = user_agent
        self.min_interval = min_interval
        self.timeout = timeout
        self._last_hit: dict[str, float] = {}
        self._intervals: dict[str, float] = {}
        self._robots: dict[str, RobotsPolicy] = {}
        self.cache_dir.mkdir(parents=True, exist_ok=True)

    def get_json(self, url: str, refresh: bool = False) -> object:
        body = self.get_bytes(url, refresh=refresh)
        try:
            return json.loads(body.decode("utf-8"))
        except json.JSONDecodeError as error:
            raise FetchError(f"Response from {url} was not JSON.") from error

    def get_bytes(self, url: str, refresh: bool = False, check_robots: bool = True) -> bytes:
        if check_robots:
            self._enforce_robots(url)
        cached = self._read_cache(url)
        if cached and not refresh:
            age = datetime.now(timezone.utc) - cached["fetched_at"]
            if age < timedelta(hours=CACHE_HOURS):
                return cached["body"]
        self._pace(url)
        request = Request(url, headers=self._headers(cached.get("etag") if cached else None))
        try:
            with urlopen(request, timeout=self.timeout) as response:
                code = response.getcode()
                if code == 304 and cached:
                    self._touch(url, cached["body"], cached.get("etag"))
                    return cached["body"]
                payload = response.read(MAX_BYTES + 1)
                if len(payload) > MAX_BYTES:
                    raise FetchError(f"Response from {url} exceeded {MAX_BYTES} bytes.")
                etag = response.headers.get("ETag")
                self._write_cache(url, payload, etag)
                return payload
        except HTTPError as error:
            if error.code == 304 and cached:
                return cached["body"]
            raise FetchError(f"HTTP {error.code} for {url}") from error
        except URLError as error:
            if cached:
                return cached["body"]
            raise FetchError(f"Could not reach {url}: {error.reason}") from error
        except TimeoutError as error:
            if cached:
                return cached["body"]
            raise FetchError(f"Timed out fetching {url}") from error

    def _enforce_robots(self, url: str) -> None:
        parsed = urlparse(url)
        origin = f"{parsed.scheme}://{parsed.netloc}"
        if origin not in self._robots:
            robots_url = origin + "/robots.txt"
            try:
                body = self.get_bytes(robots_url, refresh=False, check_robots=False)
                text = body.decode("utf-8", "replace")
            except FetchError as error:
                if "HTTP 404" in str(error):
                    text = ""
                else:
                    raise FetchError(f"Could not read robots.txt for {origin}: {error}") from error
            self._robots[origin] = parse_robots(text)
        policy = self._robots[origin]
        if not policy.allowed(url, self.user_agent):
            raise RobotsDenied(f"robots.txt disallows {url}")
        delay = policy.crawl_delay(self.user_agent)
        if delay is not None:
            host = urlparse(url).netloc
            self._intervals[host] = max(self.min_interval, min(delay, MAX_CRAWL_DELAY))

    def _headers(self, etag: str | None) -> dict[str, str]:
        headers = {
            "User-Agent": self.user_agent,
            "Accept": "application/json, text/plain;q=0.9, */*;q=0.1",
            "Accept-Encoding": "identity",
        }
        if etag:
            headers["If-None-Match"] = etag
        return headers

    def _pace(self, url: str) -> None:
        host = urlparse(url).netloc
        interval = self._intervals.get(host, self.min_interval)
        previous = self._last_hit.get(host)
        if previous is not None:
            wait = interval - (time.monotonic() - previous)
            if wait > 0:
                time.sleep(wait)
        self._last_hit[host] = time.monotonic()

    def _path(self, url: str) -> Path:
        digest = hashlib.sha256(url.encode("utf-8")).hexdigest()
        return self.cache_dir / f"{digest}.json"

    def _read_cache(self, url: str) -> dict | None:
        path = self._path(url)
        if not path.exists():
            return None
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            body = payload["body"].encode("utf-8")
            fetched = datetime.fromisoformat(payload["fetched_at"])
        except (OSError, KeyError, json.JSONDecodeError, UnicodeError, ValueError):
            return None
        return {"body": body, "etag": payload.get("etag"), "fetched_at": fetched}

    def _write_cache(self, url: str, body: bytes, etag: str | None) -> None:
        payload = {
            "url": url,
            "fetched_at": datetime.now(timezone.utc).isoformat(),
            "etag": etag,
            "body": body.decode("utf-8", "replace"),
        }
        self._path(url).write_text(json.dumps(payload), encoding="utf-8")

    def _touch(self, url: str, body: bytes, etag: str | None) -> None:
        self._write_cache(url, body, etag)
