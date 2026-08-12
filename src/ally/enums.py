"""Closed vocabularies. New variants must be handled at every match site."""

from enum import Enum


class Stage(str, Enum):
    """The six stages. Execution is unreachable before Human Strategic Lock."""

    DISCOVERY = "discovery"
    COUNSEL = "counsel"
    STRUCTURED_RETRIEVAL = "structured_retrieval"
    EVIDENCE_RECONCILIATION = "evidence_reconciliation"
    HUMAN_STRATEGIC_LOCK = "human_strategic_lock"
    EXECUTION = "execution"


class AllyPass(str, Enum):
    DISCOVERY_COUNSEL = "discovery_counsel"
    EVIDENCE_RECONCILIATION = "evidence_reconciliation"


class ClaimSource(str, Enum):
    HUMAN = "human"
    WEB = "web"
    AGENT = "agent"


class EpistemicStatus(str, Enum):
    VERIFIED = "verified"
    INFERRED = "inferred"
    UNRESOLVED = "unresolved"


class LockState(str, Enum):
    NOT_REACHED = "not_reached"
    AWAITING_SIGNATURE = "awaiting_signature"
    SIGNED = "signed"


class Genre(str, Enum):
    APPROVAL_RELEASE = "approval_release"
    MESSAGE_HOUSE = "message_house"
    MLR_CLEARED = "mlr_cleared"
    STRATEGIC_COUNSEL = "strategic_counsel"


class CritiqueCode(str, Enum):
    ADMISSIBILITY_CATALYST = "admissibility_catalyst"
    ADMISSIBILITY_TENSION = "admissibility_tension"
    CROSS_CLAIM = "cross_claim"
    ESTIMAND = "estimand"
    INTENSIFIER = "intensifier"
    GENRE = "genre"
    VOCAB_FIREWALL = "vocab_firewall"
    MISSING_EPISTEMIC = "missing_epistemic"
    IDENTITY_INFERENCE = "identity_inference"
    UNRESOLVED_OPEN = "unresolved_open"


class CorrectionCategory(str, Enum):
    VOICE_TENSE = "voice_tense"
    ADMISSIBILITY = "admissibility"
    EVIDENCE_GAP = "evidence_gap"
    CROSS_CLAIM = "cross_claim"
    ESTIMAND = "estimand"
    INTENSIFIER = "intensifier"
    GENRE = "genre"
    VOCAB_FIREWALL = "vocab_firewall"


class QuarantineReason(str, Enum):
    MISSING_EPISTEMIC = "missing_epistemic"
    VOCAB_FIREWALL = "vocab_firewall"
    IDENTITY_INFERENCE = "identity_inference"
    UNSTATED_FACT = "unstated_fact"
    CROSS_CLAIM = "cross_claim"


class EstimandBasis(str, Enum):
    TRIAL_PRODUCT = "trial_product"
    TREATMENT_POLICY = "treatment_policy"
    TREATMENT_REGIMEN = "treatment_regimen"


STAGE_ORDER: tuple[Stage, ...] = (
    Stage.DISCOVERY,
    Stage.COUNSEL,
    Stage.STRUCTURED_RETRIEVAL,
    Stage.EVIDENCE_RECONCILIATION,
    Stage.HUMAN_STRATEGIC_LOCK,
    Stage.EXECUTION,
)
