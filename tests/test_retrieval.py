"""Primary retrieval beats press-release paraphrase for estimand-bearing numbers."""

from ally.contracts import AllyMessageSpineCandidate, HumanInput, InboundEnvelope
from ally.enums import (
    ChecklistAnswer,
    ClaimSource,
    CritiqueCode,
    EpistemicStatus,
    EstimandBasis,
    Genre,
    QuarantineReason,
)
from ally.fixtures import happy_path_input
from ally.retrieval import ClinicalTrialsFixture, redefine1_weight_loss_record
from ally.runtime import run_vertical_slice


def press_weight_loss_input() -> HumanInput:
    """Happy-path spine, but efficacy arrives as an estimand-less press paraphrase."""
    return HumanInput(
        client_id="acme-pilot",
        brand_id="exampletide",
        lead_id="lead-b",
        task="Strategic diagnosis after FDA approval",
        nct_id="NCT05668715",
        spine=AllyMessageSpineCandidate(
            genre=Genre.APPROVAL_RELEASE,
            lede=(
                "The FDA has approved exampletide 2.4 mg for chronic weight management "
                "in adults with obesity."
            ),
            catalyst_external=ChecklistAnswer.YES,
            catalyst_dated=ChecklistAnswer.YES,
            catalyst_date="2026-03-12",
            tension_market_held=ChecklistAnswer.YES,
            tension_observable_marker=(
                "IQVIA TRx Feb 2026: GLP-1 obesity class share concentrated in two incumbents"
            ),
        ),
        envelopes=[
            InboundEnvelope(
                source=ClaimSource.WEB,
                epistemic=EpistemicStatus.VERIFIED,
                citation="FDA approval letter 2026-03-12",
                text=(
                    "The FDA has approved exampletide 2.4 mg for chronic weight "
                    "management in adults with obesity."
                ),
            ),
            InboundEnvelope(
                source=ClaimSource.WEB,
                epistemic=EpistemicStatus.VERIFIED,
                citation="secondary press summary",
                text="The trial showed 16.2% weight loss.",
                numeric_anchors=["16.2%"],
            ),
        ],
    )


def test_press_percent_without_primary_fails_estimand():
    session = run_vertical_slice(press_weight_loss_input())
    assert any(issue.code is CritiqueCode.ESTIMAND for issue in session.critique.issues)


def test_clinicaltrials_record_supersedes_press_paraphrase():
    session = run_vertical_slice(
        press_weight_loss_input(),
        retriever=ClinicalTrialsFixture([redefine1_weight_loss_record()]),
    )
    assert any(
        record.reason is QuarantineReason.SECONDARY_SUPERSEDED
        for record in session.quarantine
    )
    assert all(
        "The trial showed 16.2%" not in claim.text for claim in session.diagnosis.claims
    )
    assert any(
        claim.estimand is EstimandBasis.TREATMENT_POLICY and "16.2%" in claim.text
        for claim in session.diagnosis.claims
    )
    assert all(issue.code is not CritiqueCode.ESTIMAND for issue in session.critique.issues)


def test_happy_path_without_retriever_is_unchanged():
    session = run_vertical_slice(happy_path_input())
    assert session.critique.passed
