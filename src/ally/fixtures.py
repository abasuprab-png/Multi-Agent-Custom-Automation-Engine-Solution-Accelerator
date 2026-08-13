"""Eval fixtures. The GI-AE case is the planted contradiction the slice must catch."""

from ally.contracts import (
    AllyMessageSpineCandidate,
    HumanInput,
    InboundEnvelope,
    OpenVerificationItem,
)
from ally.enums import (
    ChecklistAnswer,
    ClaimSource,
    EpistemicStatus,
    EstimandBasis,
    Genre,
)


def gi_ae_contradiction_input() -> HumanInput:
    """Planted GI-AE / discontinuation contradiction plus the other recurring defects."""
    return HumanInput(
        client_id="novartis-pilot",
        brand_id="exampletide",
        lead_id="lead-a",
        task="Strategic diagnosis for an approval-adjacent obesity asset",
        open_verification=[
            OpenVerificationItem(
                id="ov-mono",
                label="monotherapy-arm-figures",
                detail="Monotherapy arm efficacy figures were never verified this session.",
            )
        ],
        spine=AllyMessageSpineCandidate(
            genre=Genre.APPROVAL_RELEASE,
            lede=(
                "A new chapter in obesity care is beginning as patients look toward "
                "next-generation options."
            ),
        ),
        envelopes=[
            InboundEnvelope(
                source=ClaimSource.WEB,
                epistemic=EpistemicStatus.VERIFIED,
                citation="REDEFINE 1 CSR Table 14.3.1",
                text=(
                    "GI adverse events occurred in 80% of treated patients versus "
                    "40% with placebo."
                ),
                numeric_anchors=["80%", "40%"],
            ),
            InboundEnvelope(
                source=ClaimSource.WEB,
                epistemic=EpistemicStatus.VERIFIED,
                citation="REDEFINE 1 CSR Table 14.3.2",
                text=(
                    "Discontinuation due to GI adverse events was 6.2% with treatment "
                    "versus 1.1% with placebo."
                ),
                numeric_anchors=["6.2%", "1.1%"],
            ),
            InboundEnvelope(
                source=ClaimSource.AGENT,
                origin_agent="drafting-specialist",
                epistemic=EpistemicStatus.INFERRED,
                text=(
                    "GI adverse events were comparable to placebo and not "
                    "treatment-limiting."
                ),
            ),
            InboundEnvelope(
                source=ClaimSource.WEB,
                epistemic=EpistemicStatus.VERIFIED,
                citation="secondary press summary",
                text="The trial showed 16.2% weight loss.",
                numeric_anchors=["16.2%"],
            ),
            InboundEnvelope(
                source=ClaimSource.AGENT,
                origin_agent="drafting-specialist",
                epistemic=EpistemicStatus.INFERRED,
                text="This is a high-precision obesity medicine.",
            ),
            InboundEnvelope(
                source=ClaimSource.AGENT,
                origin_agent="fabricated-specialist",
                epistemic=None,
                text="KOLs unanimously called the profile best-in-class.",
            ),
        ],
    )


def happy_path_input() -> HumanInput:
    """Internally consistent diagnosis that still stops at Human Strategic Lock."""
    return HumanInput(
        client_id="acme-pilot",
        brand_id="exampletide",
        lead_id="lead-b",
        task="Strategic diagnosis after FDA approval",
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
                citation="REDEFINE 1 CSR Table 11.1",
                estimand=EstimandBasis.TREATMENT_POLICY,
                numeric_anchors=["16.2%"],
                text=(
                    "Treatment-policy estimand: mean body-weight reduction was 16.2% "
                    "with exampletide versus 2.4% with placebo."
                ),
            ),
            InboundEnvelope(
                source=ClaimSource.HUMAN,
                epistemic=EpistemicStatus.VERIFIED,
                citation="lead briefing",
                text=(
                    "Payer committees are already treating GI discontinuation as the "
                    "class-level access hurdle."
                ),
            ),
        ],
    )


def underspecified_input() -> dict:
    """Raw dict missing required scope — pydantic/runtime must refuse."""
    return {
        "client_id": "",
        "brand_id": "exampletide",
        "lead_id": "lead-a",
        "task": "do something strategic",
    }
