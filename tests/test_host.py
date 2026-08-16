"""Hosted Invocations server must start without Azure and stop at the lock."""

import json
import threading
from http.client import HTTPConnection
from pathlib import Path

from ally.fixtures import gi_ae_contradiction_input
from ally.foundry import AllyInvokeRequest, InvokeOp, SessionStore, handle_invoke
from ally.foundry_project import (
    ACCOUNT_NAME,
    MODEL_DOING_DEPLOYMENT,
    MODEL_THINKING_DEPLOYMENT,
    PROJECT_ENDPOINT,
    PROJECT_NAME,
    PROJECT_RESOURCE_ID,
    RESOURCE_GROUP,
)
from ally.host import serve_stdlib


def test_host_targets_commsos_prod_not_a_second_account():
    assert ACCOUNT_NAME == "commsos-prod-resource"
    assert PROJECT_NAME == "commsos-prod"
    assert RESOURCE_GROUP == "rg-rag-prototype"
    assert PROJECT_ENDPOINT.endswith("/api/projects/commsos-prod")
    assert "commsos-prod-resource" in PROJECT_RESOURCE_ID
    assert "CommsOS-Core" not in PROJECT_RESOURCE_ID
    assert MODEL_THINKING_DEPLOYMENT == "gpt-5.6-sol"
    assert MODEL_DOING_DEPLOYMENT == "gpt-5.6-terra"


def test_session_survives_new_store_on_disk(tmp_path: Path):
    first = SessionStore(persist_dir=tmp_path)
    started = handle_invoke(
        AllyInvokeRequest(op=InvokeOp.START, human=gi_ae_contradiction_input()),
        first,
    )
    assert started.session_id is not None
    second = SessionStore(persist_dir=tmp_path)
    loaded = second.get(started.session_id)
    assert loaded is not None
    assert loaded.stage.value == "human_strategic_lock"
    assert loaded.lock is None


def test_stdlib_host_readiness_and_gi_ae_interrupt():
    store = SessionStore()
    server = serve_stdlib(store, host="127.0.0.1", port=0)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    host, port = server.server_address
    try:
        ready = HTTPConnection(host, port, timeout=5)
        ready.request("GET", "/readiness")
        ready_response = ready.getresponse()
        assert ready_response.status == 200
        assert json.loads(ready_response.read())["status"] == "ok"
        ready.close()

        body = AllyInvokeRequest(
            op=InvokeOp.START,
            human=gi_ae_contradiction_input(),
        ).model_dump_json()
        invoke = HTTPConnection(host, port, timeout=5)
        invoke.request(
            "POST",
            "/invocations?agent_session_id=sess-host-test",
            body=body,
            headers={"Content-Type": "application/json"},
        )
        invoke_response = invoke.getresponse()
        assert invoke_response.status == 200
        payload = json.loads(invoke_response.read())
        invoke.close()
        assert payload["interrupt"] is True
        assert payload["stage"] == "human_strategic_lock"
        assert payload["agent_handoff"] is None
        assert payload["error"] is None
    finally:
        server.shutdown()
        server.server_close()
