import json
import unittest
from pathlib import Path

from homecircle_feed.parsers.bmlt import parse_bmlt
from homecircle_feed.parsers.tsml import parse_tsml

FIXTURES = Path(__file__).parent / "fixtures"
LAST_SEEN = "2026-10-06T16:00:00+00:00"


class BmltParserTests(unittest.TestCase):
    def setUp(self) -> None:
        self.formats = json.loads((FIXTURES / "bmlt_formats.json").read_text(encoding="utf-8"))
        self.rows = json.loads((FIXTURES / "bmlt_meetings.json").read_text(encoding="utf-8"))
        self.result = parse_bmlt(
            self.rows,
            country="AU",
            country_default_timezone="Australia/Sydney",
            source_id="na-au-bmlt",
            source_name="NA Australia BMLT",
            source_url="https://www.na.org.au/main_server/",
            last_seen=LAST_SEEN,
            formats=self.formats,
        )
        self.by_id = {meeting["id"]: meeting for meeting in self.result.meetings}

    def test_keeps_public_meetings_and_drops_the_rest(self) -> None:
        self.assertEqual(set(self.by_id), {"na:au:3783", "na:au:2292", "na:au:3344", "na:au:90"})
        self.assertEqual(self.result.withheld["unpublished"], 1)
        self.assertEqual(self.result.withheld["outside_country"], 2)
        self.assertEqual(self.result.withheld["invalid"], 1)

    def test_sunday_in_person_perth(self) -> None:
        meeting = self.by_id["na:au:3783"]
        self.assertEqual(meeting["fellowship"], "NA")
        self.assertEqual(meeting["schedule"]["day"], "sunday")
        self.assertEqual(meeting["schedule"]["weekday"], 0)
        self.assertEqual(meeting["schedule"]["start"], "17:00")
        self.assertEqual(meeting["schedule"]["duration_minutes"], 60)
        self.assertEqual(meeting["schedule"]["timezone"], "Australia/Perth")
        self.assertEqual(meeting["schedule"]["timezone_source"], "source")
        self.assertEqual(meeting["format"], "in_person")
        self.assertEqual(meeting["location"]["suburb"], "Albany")
        self.assertEqual(meeting["location"]["state"], "WA")
        self.assertEqual(meeting["location"]["postal_code"], "6330")
        self.assertEqual(meeting["location"]["country"], "AU")
        self.assertEqual(meeting["tags"], ["open"])
        self.assertIsNone(meeting["online"]["url"])

    def test_virtual_meeting_infers_adelaide_and_strips_email(self) -> None:
        meeting = self.by_id["na:au:2292"]
        self.assertEqual(meeting["format"], "online")
        self.assertEqual(meeting["schedule"]["timezone"], "Australia/Adelaide")
        self.assertEqual(meeting["schedule"]["timezone_source"], "state")
        self.assertEqual(meeting["schedule"]["duration_minutes"], 90)
        self.assertEqual(meeting["tags"], ["open", "women", "first_nations"])
        self.assertIn("https://zoom.us/j/6865226266", meeting["online"]["url"])
        self.assertEqual(meeting["online"]["phone"], "+61871501149,,6865226266#")
        self.assertIn("[email removed]", meeting["notes"])
        self.assertNotIn("secretary@example.test", meeting["notes"])
        blob = json.dumps(meeting)
        self.assertNotIn("contact_email", blob)
        self.assertNotIn("Pat Example", blob)
        self.assertNotIn("admin_notes", blob)

    def test_polluted_city_and_hybrid_upgrade(self) -> None:
        wind_down = self.by_id["na:au:3344"]
        self.assertEqual(wind_down["location"]["suburb"], "Brisbane")
        self.assertEqual(wind_down["location"]["state"], "QLD")
        self.assertEqual(wind_down["schedule"]["timezone"], "Australia/Brisbane")
        hybrid = self.by_id["na:au:90"]
        self.assertEqual(hybrid["format"], "hybrid")
        self.assertEqual(hybrid["tags"], ["lgbtq"])


class TsmlParserTests(unittest.TestCase):
    def setUp(self) -> None:
        self.rows = json.loads((FIXTURES / "tsml_meetings.json").read_text(encoding="utf-8"))
        self.result = parse_tsml(
            self.rows,
            country="AU",
            country_default_timezone="Australia/Sydney",
            site_timezone="Australia/Sydney",
            source_id="aa-au-tsml",
            source_name="AA Australia",
            source_url="https://meetings.aa.org.au/wp-json/tsml/meetings",
            last_seen=LAST_SEEN,
        )
        self.by_id = {meeting["id"]: meeting for meeting in self.result.meetings}

    def test_withholds_inactive_and_temporarily_closed(self) -> None:
        self.assertEqual(self.result.withheld["inactive"], 1)
        self.assertEqual(self.result.withheld["temporarily_closed"], 1)
        self.assertNotIn("aa:au:9", self.by_id)
        self.assertNotIn("aa:au:10", self.by_id)

    def test_queensland_does_not_keep_the_site_timezone(self) -> None:
        meeting = self.by_id["aa:au:1"]
        self.assertEqual(meeting["fellowship"], "AA")
        self.assertEqual(meeting["schedule"]["day"], "monday")
        self.assertEqual(meeting["schedule"]["weekday"], 1)
        self.assertEqual(meeting["schedule"]["start"], "06:00")
        self.assertEqual(meeting["schedule"]["duration_minutes"], 60)
        self.assertEqual(meeting["schedule"]["timezone"], "Australia/Brisbane")
        self.assertEqual(meeting["schedule"]["timezone_source"], "state")
        self.assertEqual(meeting["format"], "in_person")
        self.assertEqual(meeting["location"]["suburb"], "Burleigh Heads")
        self.assertEqual(meeting["location"]["address"], "57 Tabilban St")
        self.assertEqual(meeting["location"]["state"], "QLD")
        self.assertEqual(meeting["location"]["postal_code"], "4220")
        self.assertEqual(meeting["tags"], ["open"])
        self.assertFalse(meeting["location"]["approximate"])

    def test_online_meeting_drops_personal_fields(self) -> None:
        meeting = self.by_id["aa:au:2"]
        self.assertEqual(meeting["format"], "online")
        self.assertEqual(meeting["schedule"]["timezone"], "Australia/Brisbane")
        self.assertEqual(meeting["online"]["url"], "https://zoom.us/j/2095271574")
        self.assertEqual(meeting["online"]["phone"], "+61731853730,,2095271574#")
        self.assertTrue(meeting["location"]["approximate"])
        self.assertEqual(meeting["source"]["record_url"], "https://meetings.aa.org.au/meetings/heartstarters/")
        blob = json.dumps(meeting)
        self.assertNotIn("edit_url", blob)
        self.assertNotIn("wp-admin", blob)
        self.assertNotIn("heartstarters@example.test", blob)
        self.assertNotIn("daian3", blob)
        self.assertNotIn("0420570350", blob)
        self.assertIn("[email removed]", meeting["notes"])

    def test_explicit_timezone_and_family_tag(self) -> None:
        meeting = self.by_id["aa:au:3"]
        self.assertEqual(meeting["format"], "hybrid")
        self.assertEqual(meeting["schedule"]["timezone"], "Australia/Perth")
        self.assertEqual(meeting["schedule"]["timezone_source"], "source")
        self.assertEqual(meeting["schedule"]["duration_minutes"], 90)
        self.assertEqual(meeting["tags"], ["closed", "women", "lgbtq", "first_nations", "families"])
        self.assertEqual(meeting["location"]["suburb"], "Fremantle")

    def test_overnight_duration(self) -> None:
        meeting = self.by_id["aa:au:4"]
        self.assertEqual(meeting["schedule"]["duration_minutes"], 90)
        self.assertEqual(meeting["schedule"]["timezone"], "Australia/Darwin")


if __name__ == "__main__":
    unittest.main()
