"""Sessions survive a cold start when keyed by diagnosis.digest()."""

import base64
import json

import httpx

from ally.durable import (
    BlobDurableBackend,
    CosmosDurableBackend,
    FallbackDurableBackend,
    MemoryDurableBackend,
)
from ally.enums import Stage
from ally.fixtures import gi_ae_contradiction_input, happy_path_input
from ally.foundry import AllyInvokeRequest, InvokeOp, SessionStore, handle_invoke
from ally.lock import signed_lock


def test_cold_start_reloads_lock_open_verification_and_digest():
    backend = MemoryDurableBackend()
    first = SessionStore(durable=backend)
    started = handle_invoke(
        AllyInvokeRequest(op=InvokeOp.START, human=gi_ae_contradiction_input()),
        first,
    )
    assert started.session_id is not None
    assert started.handoff is not None
    digest = started.handoff.diagnosis.digest()
    locked = handle_invoke(
        AllyInvokeRequest(
            op=InvokeOp.APPLY_LOCK,
            session_id=started.session_id,
            lock=signed_lock(
                digest,
                "lead-a",
                closed_decision_ids=[
                    point.id for point in started.handoff.open_decision_points
                ],
            ),
        ),
        first,
    )
    assert locked.error is None

    cold = SessionStore(durable=backend)
    loaded = cold.get(started.session_id)
    assert loaded is not None
    assert loaded.lock is not None
    assert loaded.lock.signed_by == "lead-a"
    assert loaded.diagnosis.digest() == digest
    assert loaded.diagnosis.unresolved_verification()
    assert any(
        item.label == "monotherapy-arm-figures"
        for item in loaded.diagnosis.open_verification
    )
    by_digest = cold.get_by_digest(digest)
    assert by_digest is not None
    assert by_digest.session_id == started.session_id
    assert by_digest.stage is Stage.HUMAN_STRATEGIC_LOCK


def test_apply_lock_after_cold_start_uses_digest_key():
    backend = MemoryDurableBackend()
    first = SessionStore(durable=backend)
    started = handle_invoke(
        AllyInvokeRequest(op=InvokeOp.START, human=happy_path_input()),
        first,
    )
    assert started.handoff is not None
    digest = started.handoff.diagnosis.digest()
    cold = SessionStore(durable=backend)
    locked = handle_invoke(
        AllyInvokeRequest(
            op=InvokeOp.APPLY_LOCK,
            diagnosis_digest=digest,
            lock=signed_lock(
                digest,
                "lead-b",
                closed_decision_ids=[
                    point.id for point in started.handoff.diagnosis.open_decision_points
                ],
            ),
        ),
        cold,
    )
    assert locked.error is None
    assert locked.session_id == started.session_id


def test_blob_fallback_when_cosmos_write_fails():
    class _Boom(MemoryDurableBackend):
        def put_json(self, *, session_id: str, digest: str, payload: str) -> None:
            raise RuntimeError("cosmos down")

    fallback = MemoryDurableBackend()
    chained = FallbackDurableBackend(_Boom(), fallback)
    first = SessionStore(durable=chained)
    started = handle_invoke(
        AllyInvokeRequest(op=InvokeOp.START, human=happy_path_input()),
        first,
    )
    assert started.session_id is not None
    assert started.diagnosis_digest is not None
    assert fallback.get_json_by_digest(started.diagnosis_digest) is not None
    cold = SessionStore(durable=fallback)
    loaded = cold.get_by_digest(started.diagnosis_digest)
    assert loaded is not None
    assert loaded.session_id == started.session_id


def test_cosmos_adapter_upserts_and_reads_by_digest():
    store: dict[str, dict] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "POST" and request.url.path.endswith("/docs"):
            body = json.loads(request.content)
            if "query" in body:
                value = body["parameters"][0]["value"]
                matches = [
                    doc
                    for doc in store.values()
                    if doc.get("diagnosis_digest") == value or doc.get("session_id") == value
                ]
                return httpx.Response(200, json={"Documents": matches})
            store[body["id"]] = body
            return httpx.Response(201, json=body)
        if request.method == "GET":
            digest = request.url.path.rsplit("/", 1)[-1]
            if digest not in store:
                return httpx.Response(404, json={})
            return httpx.Response(200, json=store[digest])
        return httpx.Response(500, json={"error": "unexpected"})

    client = httpx.Client(transport=httpx.MockTransport(handler))
    backend = CosmosDurableBackend(
        "https://ally-cosmos.test",
        key=base64.b64encode(b"test-cosmos-key-bytes-32!!").decode(),
        client=client,
    )
    payload = json.dumps({"session_id": "sess-1", "hello": "world"})
    backend.put_json(session_id="sess-1", digest="digest-1", payload=payload)
    loaded = backend.get_json_by_digest("digest-1")
    assert loaded is not None
    assert json.loads(loaded)["hello"] == "world"
    assert json.loads(backend.get_json_by_session_id("sess-1") or "{}")["hello"] == "world"


def test_blob_adapter_writes_digest_and_session_pointer():
    blobs: dict[str, str] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        name = request.url.path.split("/ally-sessions/", 1)[-1]
        if request.method == "PUT":
            blobs[name] = request.content.decode("utf-8")
            return httpx.Response(201)
        if request.method == "GET":
            if name not in blobs:
                return httpx.Response(404)
            return httpx.Response(200, text=blobs[name])
        return httpx.Response(500)

    client = httpx.Client(transport=httpx.MockTransport(handler))
    backend = BlobDurableBackend(
        "https://ally.blob.core.windows.net",
        key=base64.b64encode(b"test-blob-key-bytes-32!!!!").decode(),
        client=client,
    )
    backend.put_json(session_id="sess-2", digest="digest-2", payload='{"ok": true}')
    assert backend.get_json_by_digest("digest-2") == '{"ok": true}'
    assert backend.get_json_by_session_id("sess-2") == '{"ok": true}'


def test_unsigned_execution_still_halts_after_durable_reload():
    backend = MemoryDurableBackend()
    first = SessionStore(durable=backend)
    started = handle_invoke(
        AllyInvokeRequest(op=InvokeOp.START, human=gi_ae_contradiction_input()),
        first,
    )
    cold = SessionStore(durable=backend)
    response = handle_invoke(
        AllyInvokeRequest(op=InvokeOp.ENTER_EXECUTION, session_id=started.session_id),
        cold,
    )
    assert response.agent_handoff is None
    assert response.error_type == "LockGateError"
    assert response.stage is Stage.HUMAN_STRATEGIC_LOCK
    assert response.interrupt is True
