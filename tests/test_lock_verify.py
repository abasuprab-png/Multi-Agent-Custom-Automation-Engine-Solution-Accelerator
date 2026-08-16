"""Mismatched digests and spoofed signers must throw LockGateError."""

import pytest

from ally.contracts import HumanStrategicLock
from ally.exceptions import LockGateError
from ally.fixtures import happy_path_input
from ally.lock import (
    hmac_signature,
    issue_lock,
    mint_entra_test_token,
    signed_lock,
    verify_lock,
)
from ally.runtime import run_vertical_slice


def test_mismatched_digest_throws_lock_gate_error():
    lock = signed_lock("a" * 64, "lead-b")
    with pytest.raises(LockGateError, match="diagnosis_digest"):
        verify_lock(lock, "b" * 64)


def test_spoofed_hmac_signer_throws_lock_gate_error():
    digest = "c" * 64
    lock = HumanStrategicLock(
        diagnosis_digest=digest,
        signed_by="attacker",
        signature=hmac_signature(digest, "lead-b"),
    )
    with pytest.raises(LockGateError, match="signer"):
        verify_lock(lock, digest)


def test_arbitrary_signature_string_is_rejected():
    lock = HumanStrategicLock(
        diagnosis_digest="d" * 64,
        signed_by="lead-b",
        signature="sig-lead-b",
    )
    with pytest.raises(LockGateError, match="HMAC"):
        verify_lock(lock, "d" * 64)


def test_valid_hmac_lock_is_accepted():
    digest = "e" * 64
    lock = signed_lock(digest, "lead-b")
    verify_lock(lock, digest)


def test_entra_token_bound_to_digest_is_accepted():
    digest = "f" * 64
    token = mint_entra_test_token(diagnosis_digest=digest, signed_by="lead-b")
    lock = HumanStrategicLock(
        diagnosis_digest=digest,
        signed_by="lead-b",
        signature=token,
    )
    verify_lock(lock, digest)


def test_entra_token_with_spoofed_signer_throws():
    digest = "g" * 64
    token = mint_entra_test_token(diagnosis_digest=digest, signed_by="lead-b")
    lock = HumanStrategicLock(
        diagnosis_digest=digest,
        signed_by="attacker",
        signature=token,
    )
    with pytest.raises(LockGateError, match="Entra identity"):
        verify_lock(lock, digest)


def test_entra_token_with_mismatched_digest_claim_throws():
    digest = "h" * 64
    token = mint_entra_test_token(diagnosis_digest="i" * 64, signed_by="lead-b")
    lock = HumanStrategicLock(
        diagnosis_digest=digest,
        signed_by="lead-b",
        signature=token,
    )
    with pytest.raises(LockGateError, match="not bound to diagnosis.digest"):
        verify_lock(lock, digest)


def test_apply_lock_rejects_spoofed_signer_on_a_real_session():
    session = run_vertical_slice(happy_path_input())
    digest = session.diagnosis.digest()
    lock = HumanStrategicLock(
        diagnosis_digest=digest,
        signed_by="attacker",
        signature=hmac_signature(digest, "lead-b"),
        closed_decision_ids=[
            point.id for point in session.diagnosis.open_decision_points
        ],
    )
    with pytest.raises(LockGateError, match="signer"):
        session.apply_lock(lock)


def test_issue_lock_from_entra_bearer_matches_identity():
    digest = "j" * 64
    token = mint_entra_test_token(diagnosis_digest=digest, signed_by="lead-b")
    lock = issue_lock(
        diagnosis_digest=digest,
        signed_by="lead-b",
        authorization=f"Bearer {token}",
    )
    assert lock.signature == token
    verify_lock(lock, digest)
