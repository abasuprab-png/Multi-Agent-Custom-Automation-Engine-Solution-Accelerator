"""Hosted Lexie/RCC Invocations surface. AgentHandoff only."""

from __future__ import annotations

import json
import logging
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any
from urllib.parse import urlparse

from ally.enums import ExecutionAgent
from ally.exceptions import AllyError, RefusalError
from ally.execution import _parse_handoff, accept_handoff, assert_agent
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


def listen_port() -> int:
    return int(os.environ.get("PORT", str(DEFAULT_LISTEN_PORT)))


def execution_agent_from_env() -> ExecutionAgent | None:
    raw = os.environ.get("ALLY_AGENT", "ally").strip().lower()
    if raw == ExecutionAgent.LEXIE.value:
        return ExecutionAgent.LEXIE
    if raw == ExecutionAgent.RCC.value:
        return ExecutionAgent.RCC
    return None


def dispatch_execution(raw: bytes, expected: ExecutionAgent) -> dict:
    """Refuse anything that is not a validated, signed AgentHandoff."""
    text = raw.decode("utf-8")
    try:
        payload = json.loads(text)
    except json.JSONDecodeError as exc:
        raise RefusalError(
            f"{expected.value} accepts only a signed AgentHandoff, not free text"
        ) from exc
    if not isinstance(payload, dict):
        raise RefusalError(
            f"{expected.value} accepts only a signed AgentHandoff, not free text"
        )
    if payload.get("op"):
        raise RefusalError(
            f"{expected.value} accepts only a signed AgentHandoff envelope"
        )
    handoff_payload = payload["handoff"] if "handoff" in payload else payload
    parsed = _parse_handoff(handoff_payload)
    assert_agent(parsed, expected)
    return accept_handoff(parsed).model_dump(mode="json")


class ExecutionInvocationHandler(BaseHTTPRequestHandler):
    expected: ExecutionAgent = ExecutionAgent.LEXIE

    def log_message(self, format: str, *args: object) -> None:
        logger.info("%s - %s", self.address_string(), format % args)

    def do_GET(self) -> None:
        path = urlparse(self.path).path
        if path in {"/readiness", "/health"}:
            self._send_json(200, {"status": "ok", "agent": self.expected.value})
            return
        self._send_json(404, {"error": "not_found"})

    def do_POST(self) -> None:
        path = urlparse(self.path).path
        length = int(self.headers.get("Content-Length", "0"))
        raw = self.rfile.read(length)
        if path not in {"/invocations", f"/execution/{self.expected.value}"}:
            self._send_json(404, {"error": "not_found"})
            return
        try:
            body = dispatch_execution(raw, self.expected)
        except (AllyError, ValueError) as exc:
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


def make_execution_handler(expected: ExecutionAgent) -> type[ExecutionInvocationHandler]:
    class BoundHandler(ExecutionInvocationHandler):
        pass

    BoundHandler.expected = expected
    return BoundHandler


def serve_execution(
    expected: ExecutionAgent,
    *,
    host: str = DEFAULT_LISTEN_HOST,
    port: int | None = None,
) -> ThreadingHTTPServer:
    handler = make_execution_handler(expected)
    return ThreadingHTTPServer(
        (host, port if port is not None else listen_port()), handler
    )


def run_execution_host(expected: ExecutionAgent) -> None:
    logging.basicConfig(level=logging.INFO)
    if _use_foundry_adapter():
        _run_foundry_adapter(expected)
        return
    server = serve_execution(expected)
    logger.info(
        "%s Invocations listening on %s:%s",
        expected.value,
        *server.server_address,
    )
    server.serve_forever()


def _use_foundry_adapter() -> bool:
    if InvocationAgentServerHost is None:
        return False
    if os.environ.get("ALLY_STDLIB_HOST", "").strip().lower() in {"1", "true", "yes"}:
        return False
    return bool(os.environ.get("FOUNDRY_AGENT_NAME"))


def _run_foundry_adapter(expected: ExecutionAgent) -> None:
    app = InvocationAgentServerHost()

    @app.invoke_handler
    async def invoke(request: Request):
        raw = await request.body()
        try:
            body = dispatch_execution(raw, expected)
        except (AllyError, ValueError) as exc:
            return JSONResponse(
                status_code=400,
                content={"error_type": type(exc).__name__, "error": str(exc)},
            )
        return JSONResponse(body)

    logger.info("%s Invocations adapter on port %s", expected.value, listen_port())
    app.run()
