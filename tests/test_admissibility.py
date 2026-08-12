"""Admissibility is a checklist. Unanswered or internal catalysts cannot ship."""

from ally.contracts import AllyMessageSpineCandidate, AllyStrategicDiagnosis
from ally.critique import run_self_critique
from ally.enums import CritiqueCode, Genre
from ally.fixtures import gi_ae_contradiction_input, happy_path_input
from ally.knowledge import query_canon
from ally.runtime import run_vertical_slice


def test_canon_is_citable_not_paraphrased():
    rules = query_canon("ADM-1", "ADM-2")
    assert [rule.id for rule in rules] == ["ADM-1", "ADM-2"]
    assert "external" in rules[0].body.lower()
    assert "observable marker" in rules[1].body.lower()


def test_unanswered_admissibility_is_a_no():
    _, result = run_vertical_slice(gi_ae_contradiction_input())
    assert result.critique is not None
    codes = {issue.code for issue in result.critique.blocking}
    assert CritiqueCode.ADMISSIBILITY_CATALYST in codes
    assert CritiqueCode.ADMISSIBILITY_TENSION in codes
    assert any(issue.rule_id == "ADM-1" for issue in result.critique.issues)
    assert any(issue.rule_id == "ADM-2" for issue in result.critique.issues)


def test_internal_undated_catalyst_is_inadmissible():
    diagnosis = AllyStrategicDiagnosis(
        client_id="c",
        brand_id="b",
        lead_id="l",
        task="t",
        spine_candidates=[
            AllyMessageSpineCandidate(
                genre=Genre.APPROVAL_RELEASE,
                lede="The FDA has approved exampletide 2.4 mg for chronic weight management in adults with obesity.",
                catalyst_external=False,
                catalyst_dated=False,
                catalyst_date=None,
                tension_market_held=True,
                tension_observable_marker="IQVIA TRx",
            )
        ],
    )
    report = run_self_critique(diagnosis)
    assert any(issue.code is CritiqueCode.ADMISSIBILITY_CATALYST for issue in report.blocking)


def test_happy_path_admissibility_passes():
    _, result = run_vertical_slice(happy_path_input())
    assert result.critique is not None
    codes = {issue.code for issue in result.critique.blocking}
    assert CritiqueCode.ADMISSIBILITY_CATALYST not in codes
    assert CritiqueCode.ADMISSIBILITY_TENSION not in codes
    assert result.diagnosis is not None
    assert result.diagnosis.canon_citations == ["ADM-1", "ADM-2"]
