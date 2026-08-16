"""Patent-prosecution vocabulary is one filter, used at ingest and at critique."""

FIREWALL_TERMS: tuple[str, ...] = (
    "comprising",
    "embodiment",
    "prior art",
    "prosecution history",
    "office action",
    "freedom to operate",
    "non-obvious",
    "claim 1",
    "dependent claim",
    "independent claim",
    "patent family",
    "file wrapper",
    "means-plus-function",
)


def hits(text: str) -> list[str]:
    lowered = text.lower()
    return [term for term in FIREWALL_TERMS if term in lowered]
