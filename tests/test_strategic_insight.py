"""CCO insight is an object-model gate, not a slogan."""

from ally.contracts import StrategicInsight
from ally.enums import ChecklistAnswer, CritiqueCode, EpistemicStatus, Stage
from ally.fixtures import happy_path_input, lilly_glp1_cco_input
from ally.insight import critique_insight
from ally.runtime import run_vertical_slice


def test_missing_insight_is_a_critique_issue():
    issues = critique_insight(None)
    assert issues
    assert issues[0].code is CritiqueCode.STRATEGIC_INSIGHT
    assert issues[0].rule_id == "SI-5"


def test_consumer_only_influencers_fail_si4():
    issues = critique_insight(
        StrategicInsight(
            unmet_need="People cannot stay on therapy.",
            distinctive_solve="Dual incretin mechanism with labeled indication.",
            white_space="The public has not heard the persistence story.",
            primary_influencers=["consumers", "patients"],
            trust_dynamic="Patients will ask and then buy.",
            comparative_evidenced=ChecklistAnswer.NO,
            epistemic=EpistemicStatus.INFERRED,
        )
    )
    assert any(issue.rule_id == "SI-4" for issue in issues)


def test_better_than_anyone_without_evidence_fails_si2():
    issues = critique_insight(
        StrategicInsight(
            unmet_need="Need for durable obesity treatment.",
            distinctive_solve="This product is better than anyone else in the class.",
            white_space="Specialists have not occupied persistence.",
            primary_influencers=["endocrinologists", "PBM formulary committees"],
            trust_dynamic="HCPs and PBMs mediate coverage.",
            comparative_evidenced=ChecklistAnswer.UNANSWERED,
        )
    )
    assert any(issue.rule_id == "SI-2" for issue in issues)


def test_lilly_glp1_cco_case_has_insight_and_still_stops_at_the_lock():
    session = run_vertical_slice(lilly_glp1_cco_input())
    assert session.client_id == "lilly"
    assert session.brand_id == "tirzepatide"
    assert session.stage is Stage.HUMAN_STRATEGIC_LOCK
    assert session.lock is None
    assert session.diagnosis.insight is not None
    assert "endocrinologists" in session.diagnosis.insight.primary_influencers
    assert "PBM" in session.diagnosis.insight.trust_dynamic or "PBM" in " ".join(
        session.diagnosis.insight.primary_influencers
    )
    assert session.critique.passed
    assert "SI-1" in session.diagnosis.canon_citations
    assert session.handoff.summary.startswith("Human Strategic Lock")


def test_happy_path_now_carries_an_insight():
    session = run_vertical_slice(happy_path_input())
    assert session.critique.passed
    assert session.diagnosis.insight is not None
    assert session.diagnosis.insight.unmet_need
    assert session.stage is Stage.HUMAN_STRATEGIC_LOCK
