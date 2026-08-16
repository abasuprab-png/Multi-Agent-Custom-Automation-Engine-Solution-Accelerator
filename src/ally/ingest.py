"""Trust-boundary ingest. Untagged or illegal payloads are held, not promoted to claims."""

from __future__ import annotations

from ally.contracts import (
    Claim,
    DelegationBrief,
    InboundEnvelope,
    QuarantineRecord,
)
from ally.enums import EpistemicStatus, QuarantineReason
from ally.firewall import hits as firewall_hits
from ally.identity import unauthorized_names


def ingest_envelopes(
    envelopes: list[InboundEnvelope],
    *,
    brief: DelegationBrief | None = None,
) -> tuple[list[Claim], list[QuarantineRecord]]:
    claims: list[Claim] = []
    held: list[QuarantineRecord] = []
    for envelope in envelopes:
        item = ingest_envelope(envelope, brief=brief)
        if isinstance(item, QuarantineRecord):
            held.append(item)
        else:
            claims.append(item)
    return claims, held


def ingest_envelope(
    envelope: InboundEnvelope,
    *,
    brief: DelegationBrief | None = None,
) -> Claim | QuarantineRecord:
    """Apply the one trust rule. Source does not grant truth."""
    if envelope.epistemic is None:
        return QuarantineRecord.hold(
            envelope,
            QuarantineReason.MISSING_EPISTEMIC,
            "Payload had no verified/inferred/unresolved tag. Held, not ingested.",
        )

    blocked = firewall_hits(envelope.text)
    if blocked:
        return QuarantineRecord.hold(
            envelope,
            QuarantineReason.VOCAB_FIREWALL,
            f"Patent-prosecution vocabulary blocked on ingest: {', '.join(blocked)}",
        )

    if brief is not None:
        identity_hit = _identity_from_prose(envelope, brief)
        if identity_hit is not None:
            return identity_hit
        extra = _unstated_fact(envelope, brief)
        if extra is not None:
            return extra

    return Claim(
        text=envelope.text,
        source=envelope.source,
        epistemic=envelope.epistemic,
        origin_agent=envelope.origin_agent,
        citation=envelope.citation,
        estimand=envelope.estimand,
        numeric_anchors=list(envelope.numeric_anchors),
    )


def inferred_texts(claims: list[Claim]) -> list[str]:
    return [claim.text for claim in claims if claim.epistemic is EpistemicStatus.INFERRED]


def unresolved_texts(claims: list[Claim]) -> list[str]:
    return [
        claim.text for claim in claims if claim.epistemic is EpistemicStatus.UNRESOLVED
    ]


def _identity_from_prose(
    envelope: InboundEnvelope, brief: DelegationBrief
) -> QuarantineRecord | None:
    names = unauthorized_names(envelope.text, brief.allowed_identities)
    if not names:
        return None
    return QuarantineRecord.hold(
        envelope,
        QuarantineReason.IDENTITY_INFERENCE,
        "Delegated agent inferred identity beyond what the brief stated: "
        + ", ".join(names),
    )


def _unstated_fact(
    envelope: InboundEnvelope, brief: DelegationBrief
) -> QuarantineRecord | None:
    if not brief.stated_facts:
        return None
    stated_ids = {claim.id for claim in brief.stated_facts}
    if envelope.supports_fact_id is None:
        return QuarantineRecord.hold(
            envelope,
            QuarantineReason.UNSTATED_FACT,
            "Delegated agent introduced a claim with no supports_fact_id. "
            "Facts beyond the brief are held.",
        )
    if envelope.supports_fact_id not in stated_ids:
        return QuarantineRecord.hold(
            envelope,
            QuarantineReason.UNSTATED_FACT,
            f"supports_fact_id {envelope.supports_fact_id!r} is not a stated fact in the brief.",
        )
    return None
