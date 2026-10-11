"""Australian state names, timezones, and address fragments."""

from __future__ import annotations

import re
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

STATE_TIMEZONES = {
    "NSW": "Australia/Sydney",
    "ACT": "Australia/Sydney",
    "VIC": "Australia/Melbourne",
    "TAS": "Australia/Hobart",
    "QLD": "Australia/Brisbane",
    "SA": "Australia/Adelaide",
    "NT": "Australia/Darwin",
    "WA": "Australia/Perth",
}

STATE_ALIASES = {
    "nsw": "NSW",
    "new south wales": "NSW",
    "n.s.w.": "NSW",
    "qld": "QLD",
    "queensland": "QLD",
    "vic": "VIC",
    "victoria": "VIC",
    "wa": "WA",
    "western australia": "WA",
    "w.a.": "WA",
    "sa": "SA",
    "s.a.": "SA",
    "south australia": "SA",
    "tas": "TAS",
    "tasmania": "TAS",
    "act": "ACT",
    "australian capital territory": "ACT",
    "nt": "NT",
    "northern territory": "NT",
}

STATE_CODES = "|".join(sorted(STATE_TIMEZONES, key=len, reverse=True))
STATE_IN_TEXT_RE = re.compile(rf"\b(?P<state>{STATE_CODES})\b", re.IGNORECASE)
LOCALITY_RE = re.compile(
    rf"^(?P<locality>.*?)(?:\b(?P<state>{STATE_CODES})\b)\s*(?P<post>\d{{4}})?\s*$",
    re.IGNORECASE,
)
POSTCODE_RE = re.compile(r"\b(\d{4})\b")
# BMLT Australia's configured map centre. Meetings with no geocode are stored here.
BMLT_AU_CENTER = (-25.482951, 134.648438)
COUNTRY_NAMES = {
    "au": "AU",
    "australia": "AU",
    "aus": "AU",
}


def normalize_state(value: object) -> str | None:
    if value is None:
        return None
    key = " ".join(str(value).strip().lower().replace("&amp;", "&").split())
    if not key or key in {"state", "n/a", "na", "none", "null"}:
        return None
    return STATE_ALIASES.get(key)


def timezone_for_state(state: str | None) -> str | None:
    if not state:
        return None
    return STATE_TIMEZONES.get(state)


def is_iana(name: str | None) -> bool:
    if not name:
        return False
    try:
        ZoneInfo(name)
    except ZoneInfoNotFoundError:
        return False
    return True


def choose_timezone(
    explicit: str | None,
    state: str | None,
    country_default: str,
    site_timezone: str | None = None,
) -> tuple[str, str]:
    """Return (timezone, source).

    AA Australia stamps the WordPress site timezone (Australia/Sydney) on almost
    every meeting, including Western Australia and Queensland. A value equal to
    that site default is treated as unset so the state can supply the right zone.
    UTC is also treated as unset: a weekly local meeting is not held in UTC.
    """
    zone = (explicit or "").strip()
    site = (site_timezone or "").strip()
    if zone and is_iana(zone) and zone not in {site, "UTC"}:
        return zone, "source"
    inferred = timezone_for_state(state)
    if inferred:
        return inferred, "state"
    if zone and is_iana(zone) and zone != "UTC":
        return zone, "source"
    if is_iana(country_default):
        return country_default, "country_default"
    return "Australia/Sydney", "country_default"


def normalize_country(value: object, default: str = "AU") -> str:
    if value is None or str(value).strip() == "":
        return default
    key = str(value).strip().lower()
    if key in COUNTRY_NAMES:
        return COUNTRY_NAMES[key]
    if len(key) == 2 and key.isalpha():
        return key.upper()
    return default


def country_is_default(value: object, default: str = "AU") -> bool:
    """True when the field is blank or it names this country.

    An unrecognised country name is not treated as the default. Otherwise
    "United States" would fall through to AU.
    """
    if value is None or str(value).strip() == "":
        return True
    key = str(value).strip().lower()
    if key in COUNTRY_NAMES:
        return COUNTRY_NAMES[key] == default
    if len(key) == 2 and key.isalpha():
        return key.upper() == default
    return False


def parse_au_address(formatted: object) -> dict[str, str | None]:
    """Split a TSML formatted address into street, suburb, and postcode."""
    empty = {"address": None, "suburb": None, "postal_code": None}
    if formatted is None:
        return empty
    text = str(formatted).replace("&amp;", "&").strip()
    from homecircle_feed.text import clean_text

    text = clean_text(text) or ""
    text = re.sub(r",\s*Australia\s*$", "", text, flags=re.IGNORECASE).strip(" ,")
    if not text:
        return empty
    parts = [part.strip() for part in text.split(",") if part.strip()]
    suburb = None
    postal = None
    matched_index = None
    for index, part in enumerate(parts):
        match = LOCALITY_RE.match(part)
        if match and match.group("state"):
            locality = (match.group("locality") or "").strip(" ,")
            suburb = locality or None
            postal = match.group("post")
            matched_index = index
            break
    if postal is None:
        found = POSTCODE_RE.search(text)
        postal = found.group(1) if found else None
    street = None
    if matched_index is not None and matched_index > 0:
        street = ", ".join(parts[:matched_index])
    elif matched_index is None:
        street = text
    return {"address": street or None, "suburb": suburb or None, "postal_code": postal}


def postal_code(value: object) -> str | None:
    if value is None:
        return None
    match = POSTCODE_RE.search(str(value))
    return match.group(1) if match else None


def coordinate(value: object) -> float | None:
    if value is None or str(value).strip() == "":
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number


def coordinates(latitude: object, longitude: object) -> tuple[float | None, float | None]:
    lat = coordinate(latitude)
    lng = coordinate(longitude)
    if lat is None or lng is None:
        return None, None
    if not (-90 <= lat <= 90 and -180 <= lng <= 180):
        return None, None
    if lat == 0 and lng == 0:
        return None, None
    return round(lat, 6), round(lng, 6)


def usable_coordinates(latitude: object, longitude: object) -> tuple[float | None, float | None]:
    """Drop null-island, the Australian BMLT map centre, and pins outside Australia."""
    lat, lng = coordinates(latitude, longitude)
    if lat is None or lng is None:
        return None, None
    if abs(lat - BMLT_AU_CENTER[0]) < 0.02 and abs(lng - BMLT_AU_CENTER[1]) < 0.02:
        return None, None
    if not (-44.5 <= lat <= -10.0 and 112.0 <= lng <= 154.5):
        return None, None
    return lat, lng


def state_from_coordinates(latitude: float | None, longitude: float | None) -> str | None:
    """Coarse state for a meeting whose source left the province blank.

    Borders are approximate. Lismore stays in NSW; Caboolture stays in Queensland.
    """
    if latitude is None or longitude is None:
        return None
    lat, lng = latitude, longitude
    if not (-44.5 <= lat <= -10.0 and 112.0 <= lng <= 154.5):
        return None
    if -35.95 <= lat <= -35.12 and 148.73 <= lng <= 149.42:
        return "ACT"
    if lat <= -39.5 and 143.5 <= lng <= 148.8:
        return "TAS"
    if lng < 129.0:
        return "WA"
    if lng < 141.0:
        return "NT" if lat >= -26.0 else "SA"
    if (lng >= 153.0 and lat >= -28.2) or (lng < 153.0 and lat >= -29.0):
        return "QLD"
    if lat <= -36.2 and lng <= 150.0:
        return "VIC"
    return "NSW"
