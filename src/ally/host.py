"""Invocations HTTP host. Deterministic Ally; no model required to start."""

from __future__ import annotations

import json
import logging
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any
from urllib.parse import parse_qs, urlparse

from ally.foundry import AllyInvokeRequest, SessionStore, handle_invoke
from ally.foundry_project import DEFAULT_LISTEN_HOST, DEFAULT_LISTEN_PORT

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
        self._send_json(404, {"error": "not_found"})

    def do_POST(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path != "/invocations":
            self._send_json(404, {"error": "not_found"})
            return
        length = int(self.headers.get("Content-Length", "0"))
        raw = self.rfile.read(length)
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

    def _send_json(self, status: int, payload: dict) -> None:
        encoded = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)


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


def run_host() -> None:
    """Default entrypoint. Adapter if installed; stdlib otherwise. No model required."""
    logging.basicConfig(level=logging.INFO)
    if InvocationAgentServerHost is not None:
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
