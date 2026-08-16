"""Cryptographic Human Strategic Lock. Arbitrary signed_by strings are illegal."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import time
from typing import Any

from ally.contracts import HumanStrategicLock
from ally.exceptions import LockGateError

ENV_LOCK_HMAC_SECRET = "ALLY_LOCK_HMAC_SECRET"
ENV_ENTRA_TEST_SECRET = "ALLY_ENTRA_TEST_SECRET"
ENV_ENTRA_TENANT_ID = "ALLY_ENTRA_TENANT_ID"
ENV_ENTRA_AUDIENCE = "ALLY_ENTRA_AUDIENCE"
ENV_ENTRA_JWKS_URL = "ALLY_ENTRA_JWKS_URL"


def hmac_secret() -> str:
    secret = os.environ.get(ENV_LOCK_HMAC_SECRET, "").strip()
    if not secret:
        raise LockGateError(
            "ALLY_LOCK_HMAC_SECRET is required to bind a lock to diagnosis.digest()"
        )
    return secret


def hmac_signature(diagnosis_digest: str, signed_by: str, *, secret: str | None = None) -> str:
    key = (secret if secret is not None else hmac_secret()).encode("utf-8")
    message = f"{diagnosis_digest}|{signed_by}".encode("utf-8")
    return hmac.new(key, message, hashlib.sha256).hexdigest()


def signed_lock(
    diagnosis_digest: str,
    signed_by: str,
    *,
    closed_decision_ids: list[str] | None = None,
    secret: str | None = None,
) -> HumanStrategicLock:
    """Issue an HMAC lock bound to diagnosis.digest() and the signer identity."""
    return HumanStrategicLock(
        diagnosis_digest=diagnosis_digest,
        signed_by=signed_by,
        signature=hmac_signature(diagnosis_digest, signed_by, secret=secret),
        closed_decision_ids=list(closed_decision_ids or []),
    )


def looks_like_jwt(value: str) -> bool:
    parts = value.split(".")
    return len(parts) == 3 and value.startswith("eyJ")


def verify_lock(lock: HumanStrategicLock, expected_digest: str) -> None:
    """Fail closed. Mismatched digest or spoofed signer is LockGateError."""
    if lock.diagnosis_digest != expected_digest:
        raise LockGateError(
            "Lock diagnosis_digest does not match the session diagnosis"
        )
    if looks_like_jwt(lock.signature):
        _verify_entra(lock)
        return
    _verify_hmac(lock)


def issue_lock(
    *,
    diagnosis_digest: str,
    signed_by: str,
    closed_decision_ids: list[str] | None = None,
    authorization: str | None = None,
) -> HumanStrategicLock:
    """Host-side signer. Bearer Entra token or HMAC bound to diagnosis.digest()."""
    header = (authorization or "").strip()
    if header.lower().startswith("bearer "):
        token = header.split(" ", 1)[1].strip()
        lock = HumanStrategicLock(
            diagnosis_digest=diagnosis_digest,
            signed_by=signed_by,
            signature=token,
            closed_decision_ids=list(closed_decision_ids or []),
        )
        verify_lock(lock, diagnosis_digest)
        return lock
    lock = signed_lock(
        diagnosis_digest,
        signed_by,
        closed_decision_ids=closed_decision_ids,
    )
    verify_lock(lock, diagnosis_digest)
    return lock


def mint_entra_test_token(
    *,
    diagnosis_digest: str,
    signed_by: str,
    oid: str | None = None,
    secret: str | None = None,
    tenant_id: str | None = None,
    audience: str | None = None,
    expires_in: int = 3600,
    extra: dict[str, Any] | None = None,
) -> str:
    """HS256 OIDC-shaped token for tests. Production Entra tokens are RS256."""
    key = (secret if secret is not None else _entra_test_secret()).encode("utf-8")
    now = int(time.time())
    header = {"alg": "HS256", "typ": "JWT"}
    payload: dict[str, Any] = {
        "oid": oid or signed_by,
        "preferred_username": signed_by,
        "upn": signed_by,
        "tid": tenant_id or os.environ.get(ENV_ENTRA_TENANT_ID, "test-tenant"),
        "aud": audience or os.environ.get(ENV_ENTRA_AUDIENCE, "ally-lock"),
        "iat": now,
        "exp": now + expires_in,
        "diagnosis_digest": diagnosis_digest,
    }
    if extra:
        payload.update(extra)
    return _encode_hs256(header, payload, key)


def _verify_hmac(lock: HumanStrategicLock) -> None:
    expected = hmac_signature(lock.diagnosis_digest, lock.signed_by)
    if not hmac.compare_digest(expected, lock.signature):
        raise LockGateError(
            "Lock signature is not an HMAC bound to diagnosis.digest() for this signer"
        )


def _verify_entra(lock: HumanStrategicLock) -> None:
    claims = _decode_and_verify_jwt(lock.signature)
    token_digest = str(claims.get("diagnosis_digest") or claims.get("nonce") or "")
    if token_digest != lock.diagnosis_digest:
        raise LockGateError(
            "Entra token is not bound to diagnosis.digest()"
        )
    identities = {
        str(claims.get("oid") or "").strip(),
        str(claims.get("preferred_username") or "").strip(),
        str(claims.get("upn") or "").strip(),
        str(claims.get("email") or "").strip(),
        str(claims.get("sub") or "").strip(),
    }
    identities.discard("")
    if lock.signed_by not in identities:
        raise LockGateError(
            "Lock signed_by does not match the Entra identity on the token"
        )
    tenant = os.environ.get(ENV_ENTRA_TENANT_ID, "").strip()
    if tenant and str(claims.get("tid") or "") != tenant:
        raise LockGateError("Entra token tenant does not match ALLY_ENTRA_TENANT_ID")
    audience = os.environ.get(ENV_ENTRA_AUDIENCE, "").strip()
    if audience:
        aud = claims.get("aud")
        audiences = aud if isinstance(aud, list) else [aud]
        if audience not in {str(item) for item in audiences if item is not None}:
            raise LockGateError("Entra token audience does not match ALLY_ENTRA_AUDIENCE")
    exp = claims.get("exp")
    if exp is None or int(exp) < int(time.time()) - 30:
        raise LockGateError("Entra token is expired")


def _decode_and_verify_jwt(token: str) -> dict[str, Any]:
    try:
        header_b64, payload_b64, signature_b64 = token.split(".")
        header = json.loads(_b64url_decode(header_b64))
        payload = json.loads(_b64url_decode(payload_b64))
    except (ValueError, json.JSONDecodeError) as exc:
        raise LockGateError("Entra token is malformed") from exc
    if not isinstance(header, dict) or not isinstance(payload, dict):
        raise LockGateError("Entra token is malformed")
    alg = str(header.get("alg") or "")
    signing_input = f"{header_b64}.{payload_b64}".encode("ascii")
    signature = _b64url_decode(signature_b64)
    if alg == "HS256":
        key = _entra_test_secret().encode("utf-8")
        expected = hmac.new(key, signing_input, hashlib.sha256).digest()
        if not hmac.compare_digest(expected, signature):
            raise LockGateError("Entra token signature is invalid")
        return payload
    if alg == "RS256":
        raise LockGateError(
            "Entra RS256 verification is not configured; refuse rather than fail open"
        )
    raise LockGateError(f"Entra token alg {alg or 'missing'} is not accepted")


def _entra_test_secret() -> str:
    secret = os.environ.get(ENV_ENTRA_TEST_SECRET, "").strip()
    if not secret:
        raise LockGateError(
            "ALLY_ENTRA_TEST_SECRET is required to verify HS256 Entra-shaped tokens"
        )
    return secret


def _encode_hs256(header: dict[str, Any], payload: dict[str, Any], key: bytes) -> str:
    header_b64 = _b64url_encode(json.dumps(header, separators=(",", ":")).encode("utf-8"))
    payload_b64 = _b64url_encode(json.dumps(payload, separators=(",", ":")).encode("utf-8"))
    signing_input = f"{header_b64}.{payload_b64}".encode("ascii")
    signature = hmac.new(key, signing_input, hashlib.sha256).digest()
    return f"{header_b64}.{payload_b64}.{_b64url_encode(signature)}"


def _b64url_encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _b64url_decode(data: str) -> bytes:
    pad = "=" * (-len(data) % 4)
    return base64.urlsafe_b64decode(data + pad)
