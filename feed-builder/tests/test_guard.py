import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from homecircle_feed.pipeline import build
from homecircle_feed.seed import seed_previous
from homecircle_feed.split import write_state_feed

FIXTURES = Path(__file__).parent / "fixtures"


def registry(guard=None):
    country = {
        "code": "AU",
        "name": "Australia",
        "enabled": True,
        "default_timezone": "Australia/Sydney",
        "sources": [
            {
                "id": "na-au-bmlt",
                "kind": "bmlt",
                "name": "NA Australia BMLT",
                "enabled": True,
                "root_url": "https://www.na.org.au/main_server/",
            },
            {
                "id": "aa-au-tsml",
                "kind": "tsml",
                "name": "AA Australia",
                "enabled": True,
                "feed_url": "https://meetings.aa.org.au/wp-json/tsml/meetings",
                "site_timezone": "Australia/Sydney",
            },
        ],
    }
    if guard is not None:
        country["guard"] = guard
    return {"countries": [country], "not_used": []}


class GuardTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tsml = json.loads((FIXTURES / "tsml_meetings.json").read_text(encoding="utf-8"))
        self.bmlt = json.loads((FIXTURES / "bmlt_meetings.json").read_text(encoding="utf-8"))
        self.formats = json.loads((FIXTURES / "bmlt_formats.json").read_text(encoding="utf-8"))

    def getter(self, tsml_rows):
        def get_json(url: str):
            if "GetFormats" in url:
                return self.formats
            if "GetSearchResults" in url:
                return self.bmlt
            if url.endswith("/meetings"):
                return tsml_rows
            raise AssertionError(url)

        return get_json

    def _build(self, root: Path, reg, get_json, day: int):
        registry_path = root / "registry.json"
        curated_path = root / "curated.json"
        registry_path.write_text(json.dumps(reg), encoding="utf-8")
        curated_path.write_text(json.dumps({"items": []}), encoding="utf-8")
        return build(
            registry_path=registry_path,
            curated_path=curated_path,
            output_dir=root / "dist",
            get_json=get_json,
            check_link_urls=False,
            now=datetime(2026, 10, day, 16, 0, tzinfo=timezone.utc),
        )

    def test_big_drop_keeps_previous_rows_for_that_source(self) -> None:
        reg = registry(guard={"min_keep_ratio": 0.5, "min_previous": 2})
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            first = self._build(root, reg, self.getter(self.tsml), 5)
            self.assertEqual(first["countries"][0]["meeting_count"], 8)
            # AA suddenly returns one meeting out of four.
            second = self._build(root, reg, self.getter(self.tsml[:1]), 6)
            country = second["countries"][0]
            self.assertEqual(country["meeting_count"], 8)
            self.assertEqual(country["removed"], 0)
            aa = next(source for source in country["sources"] if source["id"] == "aa-au-tsml")
            self.assertEqual(aa["status"], "kept_previous")
            changes = json.loads((root / "dist" / "changes" / "au" / "latest.json").read_text(encoding="utf-8"))
            self.assertIn("aa-au-tsml", changes["stale_sources"])

    def test_small_drop_is_published(self) -> None:
        reg = registry(guard={"min_keep_ratio": 0.5, "min_previous": 2})
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._build(root, reg, self.getter(self.tsml), 5)
            rows = [row for row in self.tsml if row["id"] != 4]
            second = self._build(root, reg, self.getter(rows), 6)
            self.assertEqual(second["countries"][0]["removed"], 1)

    def test_default_guard_ignores_tiny_sources(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._build(root, registry(), self.getter(self.tsml), 5)
            second = self._build(root, registry(), self.getter(self.tsml[:1]), 6)
            aa = next(source for source in second["countries"][0]["sources"] if source["id"] == "aa-au-tsml")
            self.assertEqual(aa["status"], "ok")


class SeedTests(unittest.TestCase):
    def test_seed_round_trips_published_shards(self) -> None:
        tsml = json.loads((FIXTURES / "tsml_meetings.json").read_text(encoding="utf-8"))
        bmlt = json.loads((FIXTURES / "bmlt_meetings.json").read_text(encoding="utf-8"))
        formats = json.loads((FIXTURES / "bmlt_formats.json").read_text(encoding="utf-8"))

        def get_json(url: str):
            if "GetFormats" in url:
                return formats
            if "GetSearchResults" in url:
                return bmlt
            return tsml

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "registry.json").write_text(json.dumps(registry()), encoding="utf-8")
            (root / "curated.json").write_text(json.dumps({"items": []}), encoding="utf-8")
            build(
                registry_path=root / "registry.json",
                curated_path=root / "curated.json",
                output_dir=root / "dist",
                get_json=get_json,
                check_link_urls=False,
                now=datetime(2026, 10, 5, 16, 0, tzinfo=timezone.utc),
            )
            original = json.loads((root / "dist" / "au" / "meetings.json").read_text(encoding="utf-8"))
            site = root / "site" / "au"
            write_state_feed(original, site)
            result = seed_previous(site, root / "fresh")
            self.assertTrue(result["seeded"])
            seeded = json.loads((root / "fresh" / "au" / "meetings.json").read_text(encoding="utf-8"))
            by_id = {m["id"]: m for m in seeded["meetings"]}
            self.assertEqual(len(by_id), len(original["meetings"]))
            for meeting in original["meetings"]:
                self.assertEqual(by_id[meeting["id"]], meeting)
            self.assertFalse(seed_previous(site, root / "fresh")["seeded"])


if __name__ == "__main__":
    unittest.main()
