"""Map source format codes onto the small tag set the apps understand."""

from __future__ import annotations

TAG_ORDER = (
    "open",
    "closed",
    "women",
    "men",
    "lgbtq",
    "first_nations",
    "families",
)

# Meeting Guide / TSML codes. ABSI is "As Bill Sees It", not a First Nations tag.
TSML_CODE_TAGS = {
    "O": "open",
    "C": "closed",
    "W": "women",
    "M": "men",
    "LGBTQ": "lgbtq",
    "G": "lgbtq",
    "L": "lgbtq",
    "BI": "lgbtq",
    "T": "lgbtq",
    "NB": "lgbtq",
    "NDG": "first_nations",
    "N": "first_nations",
    "AL-AN": "families",
    "AL": "families",
}

# BMLT key strings seen on the Australian root, plus the shared equivalents.
BMLT_KEY_TAGS = {
    "O": "open",
    "C": "closed",
    "W": "women",
    "M": "men",
    "LGBTQI": "lgbtq",
    "LGBTQ": "lgbtq",
    "GB": "lgbtq",
    "G": "lgbtq",
    "L": "lgbtq",
    "BI": "lgbtq",
    "T": "lgbtq",
    "NB": "lgbtq",
    "INDIG": "first_nations",
    "NDG": "first_nations",
    "N": "first_nations",
}


def ordered_tags(tags: set[str]) -> list[str]:
    return [tag for tag in TAG_ORDER if tag in tags]


def tag_from_format_name(name: str) -> str | None:
    """Last-resort map when a BMLT server uses a local key we have not listed."""
    text = " ".join(name.lower().replace("/", " ").split())
    if not text:
        return None
    if "first nation" in text or "indigenous" in text or "torres strait" in text:
        return "first_nations"
    if "al-anon" in text or "alateen" in text or "families" in text or "family" in text:
        return "families"
    if "lgbt" in text or text in {"gay", "lesbian", "bisexual", "transgender", "non-binary", "nonbinary"}:
        return "lgbtq"
    if text in {"women", "womens", "women's"}:
        return "women"
    if text in {"men", "mens", "men's"}:
        return "men"
    if text == "open":
        return "open"
    if text == "closed":
        return "closed"
    return None
