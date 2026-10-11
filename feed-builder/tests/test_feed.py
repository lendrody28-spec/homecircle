import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from urllib.error import HTTPError
from zoneinfo import ZoneInfo

from homecircle_feed.changes import meeting_changes
from homecircle_feed.feed_items import FeedItemError, publish_feed_items
from homecircle_feed.http_client import allowed_by_robots
from homecircle_feed.links import BROKEN, OK, check_url, classify_http
from homecircle_feed.live import FeedUnavailable, classify, is_live, load_feed, starts_soon
from homecircle_feed.pipeline import build

FIXTURES = Path(__file__).parent / "fixtures"
UA = "HomeCircleMeetingFeed/1.0"


def meeting(meeting_id: str, **overrides):
    record = {
        "id": meeting_id,
        "fellowship": "AA",
        "name": "Example",
        "schedule": {
            "day": "sunday",
            "weekday": 0,
            "start": "17:00",
            "timezone": "Australia/Perth",
            "timezone_source": "source",
            "duration_minutes": 60,
        },
        "format": "in_person",
        "location": {
            "name": "Hall",
            "address": "1 Test St",
            "suburb": "Perth",
            "state": "WA",
            "postal_code": "6000",
            "country": "AU",
            "latitude": -31.95,
            "longitude": 115.86,
            "approximate": False,
        },
        "online": {"url": None, "phone": None},
        "tags": ["open"],
        "notes": None,
        "source": {
            "id": "aa-au-tsml",
            "name": "AA Australia",
            "url": "https://meetings.aa.org.au/wp-json/tsml/meetings",
            "record_url": None,
            "last_seen": "2026-10-05T16:00:00+00:00",
        },
    }
    record.update(overrides)
    return record


class LiveTests(unittest.TestCase):
    def test_live_and_starting_soon_use_the_meeting_zone(self) -> None:
        item = meeting("aa:au:1")
        zone = ZoneInfo("Australia/Perth")
        during = datetime(2026, 1, 18, 17, 30, tzinfo=zone)
        self.assertTrue(is_live(item, during))
        self.assertFalse(starts_soon(item, during))
        # Same instant expressed in UTC still belongs to that Perth meeting.
        self.assertTrue(is_live(item, during.astimezone(timezone.utc)))
        before = datetime(2026, 1, 18, 16, 40, tzinfo=zone)
        self.assertFalse(is_live(item, before))
        self.assertTrue(starts_soon(item, before, window_minutes=30))
        ended = datetime(2026, 1, 18, 18, 0, tzinfo=zone)
        self.assertFalse(is_live(item, ended))
        self.assertFalse(starts_soon(item, ended, window_minutes=30))

    def test_meeting_that_crosses_midnight_is_live_after_midnight(self) -> None:
        item = meeting("aa:au:2")
        item["schedule"] = {
            "day": "saturday",
            "weekday": 6,
            "start": "23:30",
            "timezone": "Australia/Brisbane",
            "timezone_source": "state",
            "duration_minutes": 90,
        }
        during = datetime(2026, 1, 18, 0, 15, tzinfo=ZoneInfo("Australia/Brisbane"))
        self.assertEqual(during.strftime("%A"), "Sunday")
        self.assertTrue(is_live(item, during))

    def test_queensland_and_sydney_differ_during_daylight_saving(self) -> None:
        qld = meeting("aa:au:qld")
        qld["schedule"] = {**qld["schedule"], "timezone": "Australia/Brisbane", "start": "19:00", "weekday": 0, "day": "sunday"}
        sydney = meeting("aa:au:syd")
        sydney["schedule"] = {**sydney["schedule"], "timezone": "Australia/Sydney", "start": "19:00", "weekday": 0, "day": "sunday"}
        # 18 Jan 2026 is a Sunday. 09:30 UTC is 19:30 in Brisbane (UTC+10)
        # and 20:30 in Sydney (UTC+11).
        instant = datetime(2026, 1, 18, 9, 30, tzinfo=timezone.utc)
        grouped = classify([qld, sydney], instant, window_minutes=30)
        self.assertEqual([item["id"] for item in grouped["live"]], ["aa:au:qld"])
        self.assertEqual(grouped["starting_soon"], [])

    def test_fetch_on_open_falls_back_to_cache(self) -> None:
        stored = {}

        def fail():
            raise OSError("offline")

        def empty():
            return None

        with self.assertRaises(FeedUnavailable):
            load_feed(fail, empty, stored.__setitem__)

        body = json.dumps({"meetings": [meeting("aa:au:1")]})

        def write(text: str) -> None:
            stored["body"] = text

        payload, origin = load_feed(lambda: body, lambda: stored.get("body"), write)
        self.assertEqual(origin, "network")
        self.assertEqual(payload["meetings"][0]["id"], "aa:au:1")

        cached, origin = load_feed(fail, lambda: stored["body"], write)
        self.assertEqual(origin, "cache")
        self.assertEqual(cached["meetings"][0]["id"], "aa:au:1")


class ChangeTests(unittest.TestCase):
    def test_added_removed_and_changed_ignore_last_seen(self) -> None:
        previous = [meeting("aa:au:1"), meeting("aa:au:2", name="Old")]
        current_kept = meeting("aa:au:2", name="New")
        current_kept["source"] = {**current_kept["source"], "last_seen": "2026-10-06T16:00:00+00:00"}
        untouched = meeting("aa:au:3")
        untouched["source"] = {**untouched["source"], "last_seen": "2026-10-06T16:00:00+00:00"}
        previous.append(meeting("aa:au:3"))
        delta = meeting_changes(previous, [current_kept, untouched])
        self.assertEqual([item["id"] for item in delta["removed"]], ["aa:au:1"])
        self.assertEqual(delta["added"], [])
        self.assertEqual(delta["changed"][0]["id"], "aa:au:2")
        self.assertEqual(delta["changed"][0]["fields"], ["name"])


class RobotsTests(unittest.TestCase):
    def test_na_australia_allows_the_semantic_api(self) -> None:
        text = (FIXTURES / "robots_na.txt").read_text(encoding="utf-8")
        self.assertTrue(allowed_by_robots(text, "https://www.na.org.au/main_server/client_interface/json/?switcher=GetSearchResults", UA))
        self.assertFalse(allowed_by_robots(text, "https://www.na.org.au/meetings/", UA))

    def test_aa_australia_allows_the_tsml_feed(self) -> None:
        text = (FIXTURES / "robots_aa.txt").read_text(encoding="utf-8")
        self.assertTrue(allowed_by_robots(text, "https://meetings.aa.org.au/wp-json/tsml/meetings", UA))
        self.assertFalse(allowed_by_robots(text, "https://meetings.aa.org.au/wp-admin/post.php?post=1", UA))
        self.assertTrue(allowed_by_robots(text, "https://meetings.aa.org.au/wp-admin/admin-ajax.php?action=meetings", UA))


class LinkTests(unittest.TestCase):
    def test_http_classes(self) -> None:
        self.assertEqual(classify_http(200).status, OK)
        self.assertEqual(classify_http(404).status, BROKEN)
        self.assertEqual(classify_http(403).status, "blocked_by_host")
        self.assertIsNone(classify_http(405))

    def test_check_url_marks_404_broken(self) -> None:
        def opener(request, timeout):
            raise HTTPError(request.full_url, 404, "missing", hdrs=None, fp=None)

        status = check_url("https://example.test/missing", opener)
        self.assertEqual(status.status, BROKEN)
        self.assertEqual(status.reason, "http_404")


class FeedItemTests(unittest.TestCase):
    def test_unapproved_items_are_withheld(self) -> None:
        payload, withheld = publish_feed_items(
            [
                {
                    "id": "one",
                    "publisher": "Lifeline",
                    "kind": "resource",
                    "title": "Lifeline",
                    "summary": "Call 13 11 14",
                    "url": "https://www.lifeline.org.au/",
                    "approved": False,
                },
                {
                    "id": "two",
                    "publisher": "AA Australia",
                    "kind": "news",
                    "title": "A reviewed note",
                    "summary": "Checked by a person.",
                    "url": "https://aa.org.au/",
                    "starts_at": None,
                    "ends_at": None,
                    "approved": True,
                    "review_note": "do not publish this note",
                },
            ],
            "2026-10-06T16:00:00+00:00",
        )
        self.assertEqual(withheld, 1)
        self.assertEqual(payload["item_count"], 1)
        self.assertEqual(payload["items"][0]["id"], "two")
        self.assertNotIn("review_note", payload["items"][0])

    def test_missing_flag_is_an_error(self) -> None:
        with self.assertRaises(FeedItemError):
            publish_feed_items([{"id": "x", "publisher": "AA Australia", "title": "T", "url": "https://aa.org.au/"}], "now")


class PipelineTests(unittest.TestCase):
    def test_build_writes_country_files_and_carries_a_failed_source(self) -> None:
        tsml = json.loads((FIXTURES / "tsml_meetings.json").read_text(encoding="utf-8"))
        bmlt = json.loads((FIXTURES / "bmlt_meetings.json").read_text(encoding="utf-8"))
        formats = json.loads((FIXTURES / "bmlt_formats.json").read_text(encoding="utf-8"))
        calls = {"bmlt": 0}

        def get_json(url: str):
            if "GetFormats" in url:
                return formats
            if "GetSearchResults" in url:
                calls["bmlt"] += 1
                if calls["bmlt"] > 1:
                    raise OSError("root server down")
                return bmlt
            if url.endswith("/meetings"):
                return tsml
            raise AssertionError(url)

        registry = {
            "countries": [
                {
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
            ],
            "not_used": [{"id": "virtual-na", "reason": "not country scoped"}],
        }
        curated = {"items": [{"id": "draft", "publisher": "Lifeline", "title": "Lifeline", "url": "https://www.lifeline.org.au/", "approved": False}]}
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            registry_path = root / "registry.json"
            curated_path = root / "curated.json"
            output = root / "dist"
            registry_path.write_text(json.dumps(registry), encoding="utf-8")
            curated_path.write_text(json.dumps(curated), encoding="utf-8")
            moment = datetime(2026, 10, 5, 16, 0, tzinfo=timezone.utc)
            first = build(
                registry_path=registry_path,
                curated_path=curated_path,
                output_dir=output,
                get_json=get_json,
                check_link_urls=False,
                now=moment,
            )
            self.assertEqual(first["countries"][0]["meeting_count"], 8)
            self.assertEqual(first["countries"][0]["added"], 8)
            feed = json.loads((output / "au" / "meetings.json").read_text(encoding="utf-8"))
            self.assertEqual(feed["country"], "AU")
            self.assertEqual(len(feed["meetings"]), 8)
            coverage = json.loads((output / "au" / "coverage.json").read_text(encoding="utf-8"))
            self.assertEqual(coverage["by_fellowship"]["AA"], 4)
            self.assertEqual(coverage["by_fellowship"]["NA"], 4)
            self.assertEqual(coverage["not_used"][0]["id"], "virtual-na")
            changes = json.loads((output / "changes" / "au" / "2026-10-06.json").read_text(encoding="utf-8"))
            self.assertEqual(changes["report_day"], "2026-10-06")
            published = json.loads((output / "feed-items.json").read_text(encoding="utf-8"))
            self.assertEqual(published["items"], [])
            self.assertEqual(published["withheld_unapproved"], 1)

            def offline(url: str):
                if "GetSearchResults" in url or "GetFormats" in url:
                    raise OSError("root server down")
                if url.endswith("/meetings"):
                    return [row for row in tsml if row["id"] != 4]
                raise AssertionError(url)

            second = build(
                registry_path=registry_path,
                curated_path=curated_path,
                output_dir=output,
                get_json=offline,
                check_link_urls=False,
                now=datetime(2026, 10, 6, 16, 0, tzinfo=timezone.utc),
            )
            self.assertEqual(second["countries"][0]["removed"], 1)
            kept = json.loads((output / "au" / "meetings.json").read_text(encoding="utf-8"))
            ids = {item["id"] for item in kept["meetings"]}
            self.assertIn("na:au:3783", ids)
            self.assertNotIn("aa:au:4", ids)
            self.assertTrue(any(source["status"] == "error" for source in second["countries"][0]["sources"]))


if __name__ == "__main__":
    unittest.main()
