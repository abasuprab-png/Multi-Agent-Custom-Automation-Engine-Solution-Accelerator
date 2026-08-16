"""Short-term session memory and partitioned long-term correction store."""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Never

from pydantic import BaseModel, Field

from ally.enums import CorrectionCategory, CritiqueCode


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class CorrectionEvent(BaseModel):
    client_id: str
    category: CorrectionCategory
    note: str
    recorded_at: datetime = Field(default_factory=_utcnow)


def category_for_code(code: CritiqueCode) -> CorrectionCategory:
    if code is CritiqueCode.ADMISSIBILITY_CATALYST:
        return CorrectionCategory.ADMISSIBILITY
    if code is CritiqueCode.ADMISSIBILITY_TENSION:
        return CorrectionCategory.ADMISSIBILITY
    if code is CritiqueCode.CROSS_CLAIM:
        return CorrectionCategory.CROSS_CLAIM
    if code is CritiqueCode.ESTIMAND:
        return CorrectionCategory.ESTIMAND
    if code is CritiqueCode.INTENSIFIER:
        return CorrectionCategory.INTENSIFIER
    if code is CritiqueCode.GENRE:
        return CorrectionCategory.GENRE
    if code is CritiqueCode.VOCAB_FIREWALL:
        return CorrectionCategory.VOCAB_FIREWALL
    if code is CritiqueCode.UNRESOLVED_OPEN:
        return CorrectionCategory.EVIDENCE_GAP
    return _never(code)


def _never(value: Never) -> Never:
    raise ValueError(f"unhandled critique code: {value}")


class MemoryStore:
    """Per-client partition. Novartis pilot context never leaks into another brand."""

    def __init__(self, persist_dir: Path | str | None = None) -> None:
        self._corrections: dict[str, list[CorrectionEvent]] = {}
        self._lead_notes: dict[tuple[str, str], list[str]] = {}
        self._persist_dir = Path(persist_dir) if persist_dir is not None else None
        if self._persist_dir is not None:
            self._persist_dir.mkdir(parents=True, exist_ok=True)
            self._load()

    @classmethod
    def under_home(cls) -> MemoryStore:
        home = Path(os.environ.get("HOME", "/tmp"))
        return cls(persist_dir=home / "ally-memory")

    def record_correction(
        self, client_id: str, category: CorrectionCategory, note: str
    ) -> CorrectionEvent:
        event = CorrectionEvent(client_id=client_id, category=category, note=note)
        self._corrections.setdefault(client_id, []).append(event)
        self._flush()
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
        self._flush()

    def lead_notes(self, client_id: str, lead_id: str) -> list[str]:
        return list(self._lead_notes.get((client_id, lead_id), []))

    def _path(self) -> Path | None:
        if self._persist_dir is None:
            return None
        return self._persist_dir / "store.json"

    def _flush(self) -> None:
        path = self._path()
        if path is None:
            return
        payload = {
            "corrections": {
                client: [event.model_dump(mode="json") for event in events]
                for client, events in self._corrections.items()
            },
            "lead_notes": {
                f"{client}|{lead}": notes
                for (client, lead), notes in self._lead_notes.items()
            },
        }
        path.write_text(json.dumps(payload), encoding="utf-8")

    def _load(self) -> None:
        path = self._path()
        if path is None or not path.is_file():
            return
        payload = json.loads(path.read_text(encoding="utf-8"))
        for client, events in (payload.get("corrections") or {}).items():
            self._corrections[client] = [
                CorrectionEvent.model_validate(event) for event in events
            ]
        for key, notes in (payload.get("lead_notes") or {}).items():
            client, _, lead = key.partition("|")
            self._lead_notes[(client, lead)] = list(notes)
