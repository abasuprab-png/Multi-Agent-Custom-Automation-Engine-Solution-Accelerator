"""One trust rule. Untagged or illegal agent/web/human input is held."""

from pydantic import ValidationError

import pytest

from ally.contracts import Claim, DelegationBrief, HumanInput, InboundEnvelope
from ally.enums import ClaimSource, EpistemicStatus, QuarantineReason
from ally.fixtures import gi_ae_contradiction_input, underspecified_input
from ally.ingest import ingest_envelope
from ally.runtime import run_vertical_slice


def test_untagged_agent_output_is_quarantined():
    session, result = run_vertical_slice(gi_ae_contradiction_input())
    reasons = {record.reason for record in result.quarantine}
    assert QuarantineReason.MISSING_EPISTEMIC in reasons
    held = [record for record in session.quarantine if record.reason is QuarantineReason.MISSING_EPISTEMIC]
    assert any("best-in-class" in record.text for record in held)
    assert result.diagnosis is not None
    assert all("unanimously" not in claim.text for claim in result.diagnosis.claims)


def test_human_web_and_agent_use_the_same_epistemic_field():
    tagged = [
        InboundEnvelope(
            source=source,
            epistemic=EpistemicStatus.INFERRED,
            text="A dated competitor label change is the catalyst.",
        )
        for source in (ClaimSource.HUMAN, ClaimSource.WEB, ClaimSource.AGENT)
    ]
    for envelope in tagged:
        result = ingest_envelope(envelope)
        assert isinstance(result, Claim)
        assert result.epistemic is EpistemicStatus.INFERRED
        assert result.source is envelope.source


def test_source_does_not_default_to_verified():
    envelope = InboundEnvelope(
        source=ClaimSource.HUMAN,
        text="The human said it, so it must be true.",
    )
    result = ingest_envelope(envelope)
    assert result.reason is QuarantineReason.MISSING_EPISTEMIC


def test_delegation_identity_inference_is_quarantined():
    brief = DelegationBrief(
        task="Summarize the verified claims",
        stated_facts=[],
        allowed_identities=["Jane Lead"],
        unresolved=["monotherapy-arm-figures"],
        inferred=[],
    )
    envelope = InboundEnvelope(
        source=ClaimSource.AGENT,
        origin_agent="specialist",
        epistemic=EpistemicStatus.INFERRED,
        text="Dr. Invented endorsed the asset.",
        inferred_identity="Dr. Invented",
    )
    result = ingest_envelope(envelope, brief=brief)
    assert result.reason is QuarantineReason.IDENTITY_INFERENCE


def test_delegation_extra_facts_are_quarantined():
    fact = Claim(
        text="FDA approved the product on 2026-03-12.",
        source=ClaimSource.WEB,
        epistemic=EpistemicStatus.VERIFIED,
    )
    brief = DelegationBrief(task="rewrite", stated_facts=[fact], allowed_identities=[])
    envelope = InboundEnvelope(
        source=ClaimSource.AGENT,
        origin_agent="specialist",
        epistemic=EpistemicStatus.INFERRED,
        text="Also, peak sales will be $8bn.",
        extra_facts=["peak sales will be $8bn"],
    )
    result = ingest_envelope(envelope, brief=brief)
    assert result.reason is QuarantineReason.UNSTATED_FACT


def test_patent_vocab_is_blocked_on_ingest():
    envelope = InboundEnvelope(
        source=ClaimSource.WEB,
        epistemic=EpistemicStatus.VERIFIED,
        text="The composition comprising the embodiment of claim 1 is non-obvious over the prior art.",
    )
    result = ingest_envelope(envelope)
    assert result.reason is QuarantineReason.VOCAB_FIREWALL


def test_underspecified_input_is_refused():
    with pytest.raises(ValidationError):
        HumanInput.model_validate(underspecified_input())
