"""Primary regulatory retrieval supersedes press paraphrase without a live network."""

from ally.clinical import PrimaryRegulatoryRetriever
from ally.contracts import InboundEnvelope
from ally.enums import ClaimSource, CritiqueCode, EpistemicStatus, EstimandBasis, QuarantineReason
from ally.retrieval import RetrievalQuery
from ally.runtime import run_vertical_slice
from tests.test_retrieval import press_weight_loss_input


class _FixedTrials:
    def fetch(self, query: RetrievalQuery):
        del query
        return [
            InboundEnvelope(
                source=ClaimSource.WEB,
                epistemic=EpistemicStatus.VERIFIED,
                citation="ClinicalTrials.gov NCT05668715",
                estimand=EstimandBasis.TREATMENT_POLICY,
                numeric_anchors=["16.2%", "2.4%"],
                text=(
                    "Treatment-policy estimand: mean body-weight reduction was 16.2% "
                    "with exampletide versus 2.4% with placebo."
                ),
            )
        ]


class _NoLabels:
    def fetch(self, query: RetrievalQuery):
        del query
        return []


def test_primary_retriever_port_supersedes_press():
    session = run_vertical_slice(
        press_weight_loss_input(),
        retriever=PrimaryRegulatoryRetriever(trials=_FixedTrials(), labels=_NoLabels()),
    )
    assert any(
        record.reason is QuarantineReason.SECONDARY_SUPERSEDED
        for record in session.quarantine
    )
    assert all(issue.code is not CritiqueCode.ESTIMAND for issue in session.critique.issues)
