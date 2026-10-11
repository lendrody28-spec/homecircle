"""Text cleanup for public meeting fields. Drops republished email addresses."""

from __future__ import annotations

import html
import re

EMAIL_RE = re.compile(r"[A-Z0-9._%+\-]+@[A-Z0-9.\-]+\.[A-Z]{2,}", re.IGNORECASE)
WHITESPACE_RE = re.compile(r"[ \t]+")
BLANK_LINES_RE = re.compile(r"\n{3,}")


def clean_text(value: object) -> str | None:
    if value is None:
        return None
    text = html.unescape(str(value)).replace("\r\n", "\n").replace("\r", "\n").strip()
    if not text:
        return None
    return text


def public_notes(*parts: object, limit: int = 2000) -> str | None:
    chunks: list[str] = []
    for part in parts:
        text = clean_text(part)
        if text:
            chunks.append(text)
    if not chunks:
        return None
    text = "\n".join(chunks)
    text = EMAIL_RE.sub("[email removed]", text)
    text = BLANK_LINES_RE.sub("\n\n", text).strip()
    if len(text) > limit:
        text = text[: limit - 1].rstrip() + "…"
    return text or None


def tidy_place(value: object) -> str | None:
    """A suburb or venue name. Cuts join-instructions that were pasted into the city field."""
    text = clean_text(value)
    if not text:
        return None
    text = re.split(r"\b(?:meeting\s*id|password|passcode|zoom)\b", text, maxsplit=1, flags=re.IGNORECASE)[0]
    text = text.split(",")[0]
    text = re.sub(
        r"\b(?:queensland|new south wales|victoria|western australia|south australia|tasmania|northern territory|australia)\b",
        "",
        text,
        flags=re.IGNORECASE,
    )
    text = re.sub(r"\b\d{4}\b", "", text)
    text = WHITESPACE_RE.sub(" ", text).strip(" ,.-")
    if len(text) < 2:
        return None
    if text.isupper():
        text = text.title()
    return text
