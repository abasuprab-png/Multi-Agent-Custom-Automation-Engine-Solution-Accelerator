"""Web hits and CAMS reads are tagged envelopes. CAMS write is locked."""

import pytest

from ally.cams import FixtureCamsReader, cams_envelope, refuse_cams_write
from ally.enums import EpistemicStatus, QuarantineReason
from ally.exceptions import LockGateError
from ally.fixtures import happy_path_input
from ally.runtime import run_vertical_slice
from ally.web import StaticSearcher
from ally.contracts import InboundEnvelope
from ally.enums import ClaimSource


def test_web_search_hits_are_unresolved_not_ground_truth():
    searcher = StaticSearcher(
        [
            InboundEnvelope(
                source=ClaimSource.WEB,
                epistemic=EpistemicStatus.UNRESOLVED,
                citation="https://example.com/press",
                text="Secondary writeup said weight loss was 22%.",
                numeric_anchors=["22%"],
            )
        ]
    )
    session = run_vertical_slice(happy_path_input(), searcher=searcher)
    assert any(
        claim.epistemic is EpistemicStatus.UNRESOLVED and "22%" in claim.text
        for claim in session.diagnosis.claims
    )


def test_cams_is_read_only_and_reference():
    reader = FixtureCamsReader(
        {
            ("acme-pilot", "exampletide"): [
                cams_envelope("Prior Q&A said GI is class-level.", citation="CAMS qna-12")
            ]
        }
    )
    session = run_vertical_slice(happy_path_input(), cams=reader)
    assert any("CAMS qna-12" == claim.citation for claim in session.diagnosis.claims)
    with pytest.raises(LockGateError):
        refuse_cams_write()


def test_firewall_still_holds_web_prosecution_vocab():
    searcher = StaticSearcher(
        [
            InboundEnvelope(
                source=ClaimSource.WEB,
                epistemic=EpistemicStatus.VERIFIED,
                citation="https://example.com/patent",
                text="The embodiment in claim 1 is non-obvious over prior art.",
            )
        ]
    )
    session = run_vertical_slice(happy_path_input(), searcher=searcher)
    assert any(
        record.reason is QuarantineReason.VOCAB_FIREWALL for record in session.quarantine
    )
