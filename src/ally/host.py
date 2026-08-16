"""Invocations HTTP host. Deterministic Ally; no model required to start."""

from __future__ import annotations

import json
import logging
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

from ally.enums import ExecutionAgent
from ally.exceptions import AllyError
from ally.execution import _parse_handoff, accept_handoff, assert_agent
from ally.execution_host import execution_agent_from_env, run_execution_host
from ally.fixtures import (
    gi_ae_contradiction_input,
    happy_path_input,
    lilly_glp1_cco_input,
)
from ally.foundry import AllyInvokeRequest, SessionStore, handle_invoke
from ally.foundry_project import DEFAULT_LISTEN_HOST, DEFAULT_LISTEN_PORT
from ally.lock import issue_lock

try:
    from azure.ai.agentserver.invocations import InvocationAgentServerHost
    from starlette.requests import Request
    from starlette.responses import JSONResponse
except ImportError:
    InvocationAgentServerHost = None
    Request = Any
    JSONResponse = Any

logger = logging.getLogger(__name__)
STORE = SessionStore.under_home()
STATIC_DIR = Path(__file__).resolve().parent / "static"


def listen_port() -> int:
    return int(os.environ.get("PORT", str(DEFAULT_LISTEN_PORT)))


def dispatch(raw: bytes, store: SessionStore, *, session_id: str | None) -> dict:
    payload = AllyInvokeRequest.model_validate_json(raw)
    if payload.session_id is None and session_id:
        payload = payload.model_copy(update={"session_id": session_id})
    return handle_invoke(payload, store).model_dump(mode="json")


class AllyInvocationHandler(BaseHTTPRequestHandler):
    """Stdlib Invocations surface used when the Foundry adapter is not installed."""

    store: SessionStore = STORE

    def log_message(self, format: str, *args: object) -> None:
        logger.info("%s - %s", self.address_string(), format % args)

    def do_GET(self) -> None:
        path = urlparse(self.path).path
        if path in {"/readiness", "/health"}:
            self._send_json(200, {"status": "ok"})
            return
        if path in {"/", "/lock", "/lock.html"}:
            self._send_file(STATIC_DIR / "lock.html", "text/html; charset=utf-8")
            return
        if path == "/fixtures/gi-ae":
            self._send_json(200, gi_ae_contradiction_input().model_dump(mode="json"))
            return
        if path == "/fixtures/happy":
            self._send_json(200, happy_path_input().model_dump(mode="json"))
            return
        if path == "/fixtures/lilly-glp1":
            self._send_json(200, lilly_glp1_cco_input().model_dump(mode="json"))
            return
        if path.startswith("/digest/"):
            session_id = path.split("/digest/", 1)[1]
            session = self.store.get(session_id)
            if session is None:
                self._send_json(404, {"error": "unknown session"})
                return
            self._send_json(200, {"digest": session.diagnosis.digest()})
            return
        self._send_json(404, {"error": "not_found"})

    def do_POST(self) -> None:
        parsed = urlparse(self.path)
        length = int(self.headers.get("Content-Length", "0"))
        raw = self.rfile.read(length)
        if parsed.path == "/invocations":
            query = parse_qs(parsed.query)
            session_id = (query.get("agent_session_id") or [None])[0]
            try:
                body = dispatch(raw, self.store, session_id=session_id)
            except Exception as exc:
                self._send_json(
                    400,
                    {"error_type": type(exc).__name__, "error": str(exc)},
                )
                return
            self._send_json(200, body)
            return
        if parsed.path == "/lock/sign":
            try:
                body = json.loads(raw.decode("utf-8") or "{}")
                session_id = str(body.get("session_id") or "")
                session = self.store.get(session_id)
                if session is None:
                    digest = str(body.get("diagnosis_digest") or "")
                    session = self.store.get_by_digest(digest) if digest else None
                if session is None:
                    self._send_json(404, {"error_type": "SequenceLockError", "error": "unknown session"})
                    return
                lock = issue_lock(
                    diagnosis_digest=session.diagnosis.digest(),
                    signed_by=str(body.get("signed_by") or ""),
                    closed_decision_ids=list(body.get("closed_decision_ids") or []),
                    authorization=self.headers.get("Authorization"),
                )
            except (AllyError, ValueError, json.JSONDecodeError) as exc:
                self._send_json(
                    400,
                    {"error_type": type(exc).__name__, "error": str(exc)},
                )
                return
            self._send_json(200, {"lock": lock.model_dump(mode="json")})
            return
        if parsed.path in {"/execution/lexie", "/execution/rcc"}:
            expected = (
                ExecutionAgent.LEXIE
                if parsed.path.endswith("lexie")
                else ExecutionAgent.RCC
            )
            try:
                handoff = _parse_handoff(raw.decode("utf-8"))
                assert_agent(handoff, expected)
                accepted = accept_handoff(handoff)
            except (AllyError, ValueError) as exc:
                self._send_json(
                    400,
                    {"error_type": type(exc).__name__, "error": str(exc)},
                )
                return
            self._send_json(200, accepted.model_dump(mode="json"))
            return
        self._send_json(404, {"error": "not_found"})

    def _send_json(self, status: int, payload: dict) -> None:
        encoded = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)

    def _send_file(self, path: Path, content_type: str) -> None:
        if not path.is_file():
            self._send_json(404, {"error": "not_found"})
            return
        data = path.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)


def make_handler(store: SessionStore) -> type[AllyInvocationHandler]:
    class BoundHandler(AllyInvocationHandler):
        pass

    BoundHandler.store = store
    return BoundHandler


def serve_stdlib(
    store: SessionStore | None = None,
    *,
    host: str = DEFAULT_LISTEN_HOST,
    port: int | None = None,
) -> ThreadingHTTPServer:
    handler = make_handler(store or STORE)
    server = ThreadingHTTPServer((host, port if port is not None else listen_port()), handler)
    return server


def use_foundry_adapter() -> bool:
    if InvocationAgentServerHost is None:
        return False
    if os.environ.get("ALLY_STDLIB_HOST", "").strip().lower() in {"1", "true", "yes"}:
        return False
    return bool(os.environ.get("FOUNDRY_AGENT_NAME"))


def run_host() -> None:
    """Default entrypoint. Adapter only inside a Foundry hosted sandbox."""
    logging.basicConfig(level=logging.INFO)
    execution_agent = execution_agent_from_env()
    if execution_agent is not None:
        run_execution_host(execution_agent)
        return
    if use_foundry_adapter():
        _run_foundry_adapter()
        return
    server = serve_stdlib()
    logger.info("Ally Invocations listening on %s:%s", *server.server_address)
    server.serve_forever()


def _run_foundry_adapter() -> None:
    app = InvocationAgentServerHost()

    @app.invoke_handler
    async def invoke(request: Request):
        raw = await request.body()
        session_id = getattr(request.state, "session_id", None)
        try:
            body = dispatch(raw, STORE, session_id=session_id)
        except Exception as exc:
            return JSONResponse(
                status_code=400,
                content={"error_type": type(exc).__name__, "error": str(exc)},
            )
        return JSONResponse(body)

    logger.info("Ally Invocations adapter on port %s", listen_port())
    app.run()
