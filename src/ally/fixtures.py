"""Eval fixtures. The GI-AE case is the planted contradiction the slice must catch."""

from ally.contracts import (
    AllyMessageSpineCandidate,
    HumanInput,
    InboundEnvelope,
    OpenVerificationItem,
    StrategicInsight,
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
        insight=StrategicInsight(
            unmet_need=(
                "People who start a GLP-1 often cannot stay on it or get it covered, "
                "so the clinical need is durable, tolerable, accessible obesity treatment."
            ),
            distinctive_solve=(
                "Treatment-policy estimand: mean body-weight reduction was 16.2% "
                "with exampletide versus 2.4% with placebo."
            ),
            white_space=(
                "Payer and specialist minds still treat GI discontinuation as an "
                "unsolved class hurdle rather than a product-specific persistence story."
            ),
            primary_influencers=[
                "obesity-medicine specialists",
                "PBM formulary committees",
                "endocrinologists",
            ],
            trust_dynamic=(
                "Specialists and PBMs mediate whether consumer demand becomes a "
                "prescribed, covered therapy."
            ),
            consumer_pressure=(
                "Consumers are initiating GLP-1 demand; that does not replace HCP/payer trust."
            ),
            comparative_evidenced=ChecklistAnswer.NO,
            epistemic=EpistemicStatus.VERIFIED,
        ),
    )


def lilly_glp1_cco_input() -> HumanInput:
    """Design-center case: CCO counsel for global GLP-1 communications.

    Competitive rank is not supplied. Insight is method, not landscape.
    """
    return HumanInput(
        client_id="lilly",
        brand_id="tirzepatide",
        lead_id="cco-glp1",
        task="Global GLP-1 strategic communications counsel",
        spine=AllyMessageSpineCandidate(
            genre=Genre.STRATEGIC_COUNSEL,
            lede=(
                "Counsel: occupy the persistence-and-access white space with dual-incretin "
                "evidence. Do not lead with class-rank rhetoric."
            ),
        ),
        insight=StrategicInsight(
            unmet_need=(
                "People seeking obesity care can now demand a GLP-1, but many cannot "
                "get a durable, covered, tolerable regimen they will stay on."
            ),
            distinctive_solve=(
                "Dual GIP/GLP-1 agonism is the evidenced mechanism to take to "
                "specialists and payers as a persistence-and-control story, not a slogan."
            ),
            white_space=(
                "Primary influencers still collapse the category to 'the GLP-1' and have "
                "not occupied persistence, coverage, and dual-incretin distinction as "
                "the trust problem."
            ),
            primary_influencers=[
                "endocrinologists",
                "obesity-medicine KOLs",
                "PBM formulary committees",
                "patient advocacy",
            ],
            trust_dynamic=(
                "HCPs and PBMs mediate whether consumer-initiated demand becomes a "
                "prescribed, covered, continued therapy. Advocacy shapes the trust "
                "those mediators will defend."
            ),
            consumer_pressure=(
                "Consumers are driving more treatment initiation. That raises the "
                "cost of an empty specialist/payer mind, it does not replace them."
            ),
            comparative_evidenced=ChecklistAnswer.NO,
            epistemic=EpistemicStatus.INFERRED,
        ),
        envelopes=[
            InboundEnvelope(
                source=ClaimSource.HUMAN,
                epistemic=EpistemicStatus.VERIFIED,
                citation="CCO briefing 2026-08-01",
                text=(
                    "Global GLP-1 communications must hold specialist and payer trust "
                    "while consumers initiate more treatment decisions."
                ),
            ),
            InboundEnvelope(
                source=ClaimSource.WEB,
                epistemic=EpistemicStatus.VERIFIED,
                citation="FDA label tirzepatide chronic weight management",
                text=(
                    "Tirzepatide is a dual GIP and GLP-1 receptor agonist approved "
                    "for chronic weight management in adults with obesity."
                ),
            ),
            InboundEnvelope(
                source=ClaimSource.HUMAN,
                epistemic=EpistemicStatus.VERIFIED,
                citation="access working session",
                text=(
                    "PBM formulary committees and endocrinology KOLs remain the "
                    "gate between consumer demand and a covered prescription."
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
