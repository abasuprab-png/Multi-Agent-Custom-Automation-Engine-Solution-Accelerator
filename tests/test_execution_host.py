"""Hosted Lexie/RCC refuse anything but a validated, signed AgentHandoff."""

import json
import threading
from http.client import HTTPConnection

import pytest

from ally.contracts import AgentHandoff, HumanStrategicLock
from ally.enums import ExecutionAgent
from ally.exceptions import LockGateError, RefusalError
from ally.execution import accept_handoff
from ally.execution_host import dispatch_execution, serve_execution
from ally.fixtures import happy_path_input
from ally.foundry import AllyInvokeRequest, InvokeOp, SessionStore, handle_invoke
from ally.lock import signed_lock


def _signed_handoff() -> AgentHandoff:
    store = SessionStore()
    started = handle_invoke(
        AllyInvokeRequest(op=InvokeOp.START, human=happy_path_input()),
        store,
    )
    assert started.handoff is not None
    handle_invoke(
        AllyInvokeRequest(
            op=InvokeOp.APPLY_LOCK,
            session_id=started.session_id,
            lock=signed_lock(
                started.handoff.diagnosis.digest(),
                "lead-b",
                closed_decision_ids=[
                    point.id
                    for point in started.handoff.diagnosis.open_decision_points
                ],
            ),
        ),
        store,
    )
    released = handle_invoke(
        AllyInvokeRequest(
            op=InvokeOp.ENTER_EXECUTION,
            session_id=started.session_id,
            to_agent=ExecutionAgent.LEXIE,
        ),
        store,
    )
    assert released.agent_handoff is not None
    return released.agent_handoff


def test_lexie_refuses_free_text():
    with pytest.raises(RefusalError, match="AgentHandoff"):
        dispatch_execution(b"please draft the press release", ExecutionAgent.LEXIE)


def test_rcc_refuses_ally_start_op():
    body = AllyInvokeRequest(op=InvokeOp.START, human=happy_path_input()).model_dump_json()
    with pytest.raises(RefusalError, match="signed AgentHandoff"):
        dispatch_execution(body.encode("utf-8"), ExecutionAgent.RCC)


def test_lexie_refuses_unsigned_lock():
    handoff = _signed_handoff()
    spoofed = AgentHandoff(
        to_agent=ExecutionAgent.LEXIE,
        diagnosis_id=handoff.diagnosis_id,
        claims=list(handoff.claims),
        lock=HumanStrategicLock(
            diagnosis_digest=handoff.lock.diagnosis_digest,
            signed_by="attacker",
            signature="not-a-real-signature",
        ),
    )
    with pytest.raises(LockGateError):
        accept_handoff(spoofed)
    with pytest.raises(LockGateError):
        dispatch_execution(
            spoofed.model_dump_json().encode("utf-8"), ExecutionAgent.LEXIE
        )


def test_lexie_accepts_validated_signed_handoff():
    handoff = _signed_handoff()
    accepted = dispatch_execution(
        handoff.model_dump_json().encode("utf-8"), ExecutionAgent.LEXIE
    )
    assert accepted["accepted"] is True
    assert accepted["to_agent"] == "lexie"
    assert accepted["lock_signed_by"] == "lead-b"


def test_rcc_refuses_handoff_addressed_to_lexie():
    handoff = _signed_handoff()
    with pytest.raises(RefusalError, match="addressed to lexie"):
        dispatch_execution(
            handoff.model_dump_json().encode("utf-8"), ExecutionAgent.RCC
        )


def test_lexie_http_host_refuses_unsigned_and_accepts_signed():
    server = serve_execution(ExecutionAgent.LEXIE, host="127.0.0.1", port=0)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    host, port = server.server_address
    try:
        ready = HTTPConnection(host, port, timeout=5)
        ready.request("GET", "/readiness")
        ready_response = ready.getresponse()
        assert ready_response.status == 200
        assert json.loads(ready_response.read())["agent"] == "lexie"
        ready.close()

        bad = HTTPConnection(host, port, timeout=5)
        bad.request(
            "POST",
            "/invocations",
            body="unsigned free text",
            headers={"Content-Type": "application/json"},
        )
        bad_response = bad.getresponse()
        payload = json.loads(bad_response.read())
        bad.close()
        assert bad_response.status == 400
        assert payload["error_type"] == "RefusalError"

        handoff = _signed_handoff()
        ok = HTTPConnection(host, port, timeout=5)
        ok.request(
            "POST",
            "/invocations",
            body=handoff.model_dump_json(),
            headers={"Content-Type": "application/json"},
        )
        ok_response = ok.getresponse()
        accepted = json.loads(ok_response.read())
        ok.close()
        assert ok_response.status == 200
        assert accepted["accepted"] is True
    finally:
        server.shutdown()
        server.server_close()
