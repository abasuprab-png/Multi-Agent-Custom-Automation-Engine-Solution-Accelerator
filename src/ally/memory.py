"""Short-term session memory and partitioned long-term correction store."""

from __future__ import annotations

from datetime import datetime, timezone

from pydantic import BaseModel, Field

from ally.enums import CorrectionCategory


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class CorrectionEvent(BaseModel):
    client_id: str
    category: CorrectionCategory
    note: str
    recorded_at: datetime = Field(default_factory=_utcnow)


class MemoryStore:
    """Per-client partition. Novartis pilot context never leaks into another brand."""

    def __init__(self) -> None:
        self._corrections: dict[str, list[CorrectionEvent]] = {}
        self._lead_notes: dict[tuple[str, str], list[str]] = {}

    def record_correction(
        self, client_id: str, category: CorrectionCategory, note: str
    ) -> CorrectionEvent:
        event = CorrectionEvent(client_id=client_id, category=category, note=note)
        self._corrections.setdefault(client_id, []).append(event)
        return event

    def corrections_for(self, client_id: str) -> list[CorrectionEvent]:
        return list(self._corrections.get(client_id, []))

    def category_counts(self, client_id: str) -> dict[CorrectionCategory, int]:
        counts: dict[CorrectionCategory, int] = {}
        for event in self.corrections_for(client_id):
            counts[event.category] = counts.get(event.category, 0) + 1
        return counts

    def remember_lead(self, client_id: str, lead_id: str, note: str) -> None:
        """Silent preference store. Never announced, never overrides disagreement."""
        self._lead_notes.setdefault((client_id, lead_id), []).append(note)

    def lead_notes(self, client_id: str, lead_id: str) -> list[str]:
        return list(self._lead_notes.get((client_id, lead_id), []))
