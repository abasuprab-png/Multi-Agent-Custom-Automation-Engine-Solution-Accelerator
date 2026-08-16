"""Identity inference is read from prose, not from a side-channel field."""

from __future__ import annotations

import re

_TITLE = r"(?:Dr|Prof|Professor|Mr|Ms|Mrs|Mx)"
_TITLED_NAME = re.compile(
    rf"\b{_TITLE}\.?\s+[A-Z][a-zA-Z]+(?:\s+[A-Z][a-zA-Z]+)*"
)
_STRIP_TITLE = re.compile(rf"^{_TITLE}\.?\s+", re.IGNORECASE)


def titled_names(text: str) -> list[str]:
    return [match.group(0) for match in _TITLED_NAME.finditer(text)]


def unauthorized_names(text: str, allowed: list[str]) -> list[str]:
    allowed_norm = {_normalize(name) for name in allowed}
    found: list[str] = []
    for name in titled_names(text):
        if _normalize(name) not in allowed_norm:
            found.append(name)
    return found


def _normalize(name: str) -> str:
    return _STRIP_TITLE.sub("", name).strip().lower()
