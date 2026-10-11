import json
import unittest
from pathlib import Path

from homecircle_feed.geo import state_from_coordinates, usable_coordinates
from homecircle_feed.parsers.bmlt import parse_bmlt

FIXTURES = Path(__file__).parent / "fixtures"


class CoordinateStateTests(unittest.TestCase):
    def test_boxes(self) -> None:
        self.assertEqual(state_from_coordinates(-27.08, 152.93), "QLD")
        self.assertEqual(state_from_coordinates(-28.81, 153.29), "NSW")
        self.assertEqual(state_from_coordinates(-33.90, 151.18), "NSW")
        self.assertEqual(state_from_coordinates(-38.60, 145.59), "VIC")
        self.assertEqual(state_from_coordinates(-32.28, 115.74), "WA")
        self.assertEqual(state_from_coordinates(-33.03, 137.56), "SA")
        self.assertEqual(state_from_coordinates(-12.46, 130.84), "NT")
        self.assertEqual(state_from_coordinates(-42.88, 147.33), "TAS")
        self.assertEqual(state_from_coordinates(-35.28, 149.13), "ACT")
        self.assertIsNone(state_from_coordinates(38.96, -95.24))

    def test_placeholder_and_overseas_pins_are_dropped(self) -> None:
        self.assertEqual(usable_coordinates(-25.482951, 134.648438), (None, None))
        self.assertEqual(usable_coordinates(38.966351, -95.236096), (None, None))
        lat, lng = usable_coordinates(-33.895314, 151.182888)
        self.assertEqual((lat, lng), (-33.895314, 151.182888))

    def test_blank_province_uses_the_pin_for_state_and_timezone(self) -> None:
        formats = json.loads((FIXTURES / "bmlt_formats.json").read_text(encoding="utf-8"))
        result = parse_bmlt(
            [
                {
                    "id_bigint": "3681",
                    "published": "1",
                    "meeting_name": "Caboolture Monday night mens",
                    "weekday_tinyint": "2",
                    "start_time": "19:00:00",
                    "duration_time": "01:00:00",
                    "time_zone": "",
                    "venue_type": "1",
                    "formats": "M",
                    "latitude": "-27.077575",
                    "longitude": "152.931352",
                    "location_municipality": "Caboolture",
                    "location_province": "",
                    "location_nation": "AU",
                }
            ],
            country="AU",
            country_default_timezone="Australia/Sydney",
            source_id="na-au-bmlt",
            source_name="NA Australia BMLT",
            source_url="https://www.na.org.au/main_server/",
            last_seen="2026-10-06T16:00:00+00:00",
            formats=formats,
        )
        meeting = result.meetings[0]
        self.assertEqual(meeting["location"]["state"], "QLD")
        self.assertEqual(meeting["schedule"]["timezone"], "Australia/Brisbane")
        self.assertEqual(meeting["schedule"]["timezone_source"], "state")
        self.assertEqual(meeting["tags"], ["men"])


if __name__ == "__main__":
    unittest.main()
