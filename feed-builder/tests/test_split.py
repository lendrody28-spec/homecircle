import json
import tempfile
import unittest
from pathlib import Path

from homecircle_feed.split import publish_meeting, split_country, write_state_feed


def meeting(meeting_id: str, state: str | None, meeting_format: str = "in_person", source: str = "aa-au-tsml") -> dict:
    return {
        "id": meeting_id,
        "fellowship": "AA",
        "name": meeting_id,
        "schedule": {
            "day": "monday",
            "weekday": 1,
            "start": "18:00",
            "timezone": "Australia/Sydney",
            "timezone_source": "state",
            "duration_minutes": 60,
        },
        "format": meeting_format,
        "location": {
            "name": "Hall",
            "address": "1 Test St",
            "suburb": "Town",
            "state": state,
            "postal_code": "2000",
            "country": "AU",
            "latitude": -33.8,
            "longitude": 151.2,
            "approximate": False,
        },
        "online": {"url": "https://zoom.example/j/1" if meeting_format == "online" else None, "phone": None},
        "tags": ["open"],
        "notes": "x" * 80,
        "source": {
            "id": source,
            "name": "AA Australia Meeting Guide feed",
            "url": "https://meetings.aa.org.au/wp-json/tsml/meetings",
            "record_url": f"https://meetings.aa.org.au/meetings/{meeting_id}/",
            "last_seen": "2026-10-06T05:11:35+00:00",
        },
    }


def payload(rows: list[dict]) -> dict:
    return {
        "schema_version": "1.0.0",
        "country": "AU",
        "country_name": "Australia",
        "generated_at": "2026-10-06T05:11:35+00:00",
        "meeting_count": len(rows),
        "sources": [],
        "meetings": rows,
    }


class SplitTests(unittest.TestCase):
    def test_state_online_and_unknown_buckets(self) -> None:
        rows = [
            meeting("aa:au:nsw", "NSW", "online"),
            meeting("aa:au:qld", "QLD", "in_person"),
            meeting("aa:au:none", None, "online"),
            meeting("na:au:blank", None, "hybrid", source="na-au-bmlt"),
        ]
        rows[3]["source"]["name"] = "NA Australia BMLT"
        rows[3]["source"]["url"] = "https://www.na.org.au/main_server/"
        rows[3]["fellowship"] = "NA"
        packed = split_country(payload(rows), max_bytes=900_000)
        self.assertEqual(packed["index"]["meeting_count"], 4)
        files = packed["files"]
        self.assertIn("aa:au:nsw", {item["id"] for item in files["NSW.json"]["meetings"]})
        self.assertIn("aa:au:nsw", {item["id"] for item in files["online.json"]["meetings"]})
        self.assertIn("aa:au:none", {item["id"] for item in files["online.json"]["meetings"]})
        self.assertNotIn("aa:au:qld", {item["id"] for item in files["online.json"]["meetings"]})
        unknown_ids = {item["id"] for item in files["unknown.json"]["meetings"]}
        self.assertEqual(unknown_ids, {"aa:au:none", "na:au:blank"})
        self.assertNotIn("NSW", {item["id"] for item in files["unknown.json"]["meetings"]})
        states = {(item["state"], item["file"]) for item in packed["index"]["states"]}
        self.assertIn(("NSW", "NSW.json"), states)
        self.assertIn(("online", "online.json"), states)
        self.assertIn(("unknown", "unknown.json"), states)
        self.assertNotIn(("VIC", "VIC.json"), states)
        row = files["NSW.json"]["meetings"][0]
        self.assertEqual(set(row["source"]), {"id", "record_url", "last_seen"})
        self.assertEqual(files["NSW.json"]["sources"][0]["url"], "https://meetings.aa.org.au/wp-json/tsml/meetings")
        self.assertNotIn("\n", json.dumps(row))

    def test_oversized_state_is_split_and_minified(self) -> None:
        rows = [meeting(f"aa:au:{index}", "NSW") for index in range(6)]
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            (directory / "NSW-9.json").write_text("{}", encoding="utf-8")
            write_state_feed(payload(rows), directory, max_bytes=1000)
            names = sorted(path.name for path in directory.glob("*.json"))
            self.assertIn("index.json", names)
            self.assertNotIn("NSW.json", names)
            self.assertNotIn("NSW-9.json", names)
            shards = [name for name in names if name.startswith("NSW-")]
            self.assertGreaterEqual(len(shards), 2)
            index = json.loads((directory / "index.json").read_text(encoding="utf-8"))
            self.assertEqual(index["meeting_count"], 6)
            listed = [item["file"] for item in index["states"] if item["state"] == "NSW"]
            self.assertEqual(listed, shards)
            total = 0
            for name in shards:
                text = (directory / name).read_text(encoding="utf-8")
                self.assertNotIn("\n", text)
                self.assertNotRegex(text, r":\s")
                self.assertLessEqual(len(text.encode("utf-8")), 1000)
                body = json.loads(text)
                total += body["meeting_count"]
                self.assertNotIn("name", body["meetings"][0]["source"])
                self.assertNotIn("url", body["meetings"][0]["source"])
            self.assertEqual(total, 6)

    def test_publish_meeting_keeps_record_url(self) -> None:
        row = publish_meeting(meeting("aa:au:1", "ACT"))
        self.assertEqual(row["source"]["record_url"], "https://meetings.aa.org.au/meetings/aa:au:1/")
        self.assertNotIn("name", row["source"])


if __name__ == "__main__":
    unittest.main()
