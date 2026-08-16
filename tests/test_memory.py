"""Short-term unresolved items persist. Long-term memory is partitioned by client."""

from ally.enums import CorrectionCategory
from ally.fixtures import gi_ae_contradiction_input
from ally.memory import MemoryStore
from ally.runtime import run_vertical_slice


def test_monotherapy_arm_figures_do_not_vanish():
    session = run_vertical_slice(gi_ae_contradiction_input())
    labels = [item.label for item in session.diagnosis.unresolved_verification()]
    assert "monotherapy-arm-figures" in labels
    assert any(
        "monotherapy-arm-figures" in point.prompt
        for point in session.handoff.open_decision_points
    )


def test_client_partition_does_not_leak():
    store = MemoryStore()
    store.record_correction(
        "novartis-pilot",
        CorrectionCategory.GENRE,
        "Lead rejected atmospheric approval ledes",
    )
    store.remember_lead("novartis-pilot", "lead-a", "Prefers treatment-policy first")
    assert store.corrections_for("other-brand") == []
    assert store.category_counts("other-brand") == {}
    assert store.lead_notes("other-brand", "lead-a") == []
    assert store.lead_notes("novartis-pilot", "lead-a") == ["Prefers treatment-policy first"]
    assert store.category_counts("novartis-pilot")[CorrectionCategory.GENRE] == 1
