"""CAMS read access. Reference only. Write stays behind Human Strategic Lock."""

from __future__ import annotations

from typing import Protocol

from ally.contracts import InboundEnvelope
from ally.enums import ClaimSource, EpistemicStatus
from ally.exceptions import LockGateError


class CamsReader(Protocol):
    def read(self, client_id: str, brand_id: str) -> list[InboundEnvelope]:
        """Return already-tagged CAMS envelopes. Never untagged."""


class FixtureCamsReader:
    def __init__(self, records: dict[tuple[str, str], list[InboundEnvelope]]) -> None:
        self.records = records

    def read(self, client_id: str, brand_id: str) -> list[InboundEnvelope]:
        return list(self.records.get((client_id, brand_id), []))


class EmptyCamsReader:
    def read(self, client_id: str, brand_id: str) -> list[InboundEnvelope]:
        del client_id, brand_id
        return []


def refuse_cams_write() -> None:
    raise LockGateError("CAMS write is forbidden until a Human Strategic Lock exists")


def cams_envelope(text: str, *, citation: str) -> InboundEnvelope:
    return InboundEnvelope(
        source=ClaimSource.HUMAN,
        epistemic=EpistemicStatus.UNRESOLVED,
        citation=citation,
        text=text,
    )
