"""Ally runtime: typed multi-agent contracts with a hard Human Strategic Lock."""

from ally.contracts import (
    AgentHandoff,
    AllyMessageSpineCandidate,
    AllyStrategicDiagnosis,
    Claim,
    CritiqueReport,
    DelegationBrief,
    HumanHandoff,
    HumanInput,
    HumanStrategicLock,
    InboundEnvelope,
    SliceResult,
)
from ally.enums import (
    AllyPass,
    ClaimSource,
    CritiqueCode,
    EpistemicStatus,
    EstimandBasis,
    Genre,
    LockState,
    Stage,
)
from ally.exceptions import LockGateError, RefusalError, SequenceLockError
from ally.memory import MemoryStore
from ally.prompts import SYSTEM_PROMPT
from ally.runtime import AllySession, diagnosis_digest, run_vertical_slice

__all__ = [
    "AgentHandoff",
    "AllyMessageSpineCandidate",
    "AllyPass",
    "AllySession",
    "AllyStrategicDiagnosis",
    "Claim",
    "ClaimSource",
    "CritiqueCode",
    "CritiqueReport",
    "DelegationBrief",
    "EpistemicStatus",
    "EstimandBasis",
    "Genre",
    "HumanHandoff",
    "HumanInput",
    "HumanStrategicLock",
    "InboundEnvelope",
    "LockGateError",
    "LockState",
    "MemoryStore",
    "RefusalError",
    "SYSTEM_PROMPT",
    "SequenceLockError",
    "SliceResult",
    "Stage",
    "diagnosis_digest",
    "run_vertical_slice",
]
