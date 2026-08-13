"""Trust-boundary ingest. Untagged or illegal payloads are held, not promoted to claims."""

from __future__ import annotations

from ally.contracts import (
    Claim,
    DelegationBrief,
    InboundEnvelope,
    QuarantineRecord,
)
from ally.enums import EpistemicStatus, QuarantineReason
from ally.knowledge import firewall_hits


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

    hits = firewall_hits(envelope.text)
    if hits:
        return QuarantineRecord.hold(
            envelope,
            QuarantineReason.VOCAB_FIREWALL,
            f"Patent-prosecution vocabulary blocked on ingest: {', '.join(hits)}",
        )

    if brief is not None:
        identity_hit = _identity_inference(envelope, brief)
        if identity_hit is not None:
            return identity_hit
        extra = _unstated_facts(envelope, brief)
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


def _identity_inference(
    envelope: InboundEnvelope, brief: DelegationBrief
) -> QuarantineRecord | None:
    if not envelope.inferred_identity:
        return None
    allowed = {item.lower() for item in brief.allowed_identities}
    if envelope.inferred_identity.lower() in allowed:
        return None
    return QuarantineRecord.hold(
        envelope,
        QuarantineReason.IDENTITY_INFERENCE,
        f"Delegated agent inferred identity '{envelope.inferred_identity}' "
        "beyond what the brief stated.",
    )


def _unstated_facts(
    envelope: InboundEnvelope, brief: DelegationBrief
) -> QuarantineRecord | None:
    if not envelope.extra_facts:
        return None
    stated = {claim.text.strip().lower() for claim in brief.stated_facts}
    novel = [fact for fact in envelope.extra_facts if fact.strip().lower() not in stated]
    if not novel:
        return None
    return QuarantineRecord.hold(
        envelope,
        QuarantineReason.UNSTATED_FACT,
        "Delegated agent introduced facts beyond the brief: " + "; ".join(novel),
    )
