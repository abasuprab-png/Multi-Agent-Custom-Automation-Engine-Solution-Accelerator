"""External session persistence. $HOME does not survive Foundry scale-to-zero."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
from datetime import datetime, timezone
from typing import Any, Protocol
from urllib.parse import quote, urlparse

import httpx

ENV_COSMOS_ENDPOINT = "ALLY_COSMOS_ENDPOINT"
ENV_COSMOS_KEY = "ALLY_COSMOS_KEY"
ENV_COSMOS_DATABASE = "ALLY_COSMOS_DATABASE"
ENV_COSMOS_CONTAINER = "ALLY_COSMOS_CONTAINER"
ENV_BLOB_ACCOUNT_URL = "ALLY_BLOB_ACCOUNT_URL"
ENV_BLOB_KEY = "ALLY_BLOB_ACCOUNT_KEY"
ENV_BLOB_CONTAINER = "ALLY_BLOB_CONTAINER"

DEFAULT_COSMOS_DATABASE = "ally"
DEFAULT_COSMOS_CONTAINER = "sessions"
DEFAULT_BLOB_CONTAINER = "ally-sessions"


class DurableWriteError(Exception):
    """Raised when a durable backend cannot persist a session."""


class DurableBackend(Protocol):
    def put_json(self, *, session_id: str, digest: str, payload: str) -> None:
        """Store one session snapshot. Primary key is diagnosis.digest()."""

    def get_json_by_session_id(self, session_id: str) -> str | None:
        """Return snapshot JSON or None."""

    def get_json_by_digest(self, digest: str) -> str | None:
        """Return snapshot JSON keyed by diagnosis.digest()."""


class MemoryDurableBackend:
    """In-process stand-in used by tests and as a last-resort process cache."""

    def __init__(self) -> None:
        self.by_session: dict[str, str] = {}
        self.by_digest: dict[str, str] = {}

    def put_json(self, *, session_id: str, digest: str, payload: str) -> None:
        self.by_session[session_id] = payload
        self.by_digest[digest] = payload

    def get_json_by_session_id(self, session_id: str) -> str | None:
        return self.by_session.get(session_id)

    def get_json_by_digest(self, digest: str) -> str | None:
        return self.by_digest.get(digest)


class FallbackDurableBackend:
    """Cosmos primary, Azure Blob fallback. Read tries primary then fallback."""

    def __init__(self, primary: DurableBackend, fallback: DurableBackend) -> None:
        self.primary = primary
        self.fallback = fallback

    def put_json(self, *, session_id: str, digest: str, payload: str) -> None:
        try:
            self.primary.put_json(session_id=session_id, digest=digest, payload=payload)
        except Exception as exc:
            try:
                self.fallback.put_json(
                    session_id=session_id, digest=digest, payload=payload
                )
            except Exception as fallback_exc:
                raise DurableWriteError(
                    f"durable write failed: {exc}; fallback: {fallback_exc}"
                ) from fallback_exc
            return
        try:
            self.fallback.put_json(session_id=session_id, digest=digest, payload=payload)
        except Exception:
            return

    def get_json_by_session_id(self, session_id: str) -> str | None:
        try:
            found = self.primary.get_json_by_session_id(session_id)
            if found is not None:
                return found
        except Exception:
            found = None
        return self.fallback.get_json_by_session_id(session_id)

    def get_json_by_digest(self, digest: str) -> str | None:
        try:
            found = self.primary.get_json_by_digest(digest)
            if found is not None:
                return found
        except Exception:
            found = None
        return self.fallback.get_json_by_digest(digest)


class CosmosDurableBackend:
    """Cosmos SQL REST. Documents are keyed by diagnosis.digest() and session_id."""

    def __init__(
        self,
        endpoint: str,
        *,
        key: str | None = None,
        database: str = DEFAULT_COSMOS_DATABASE,
        container: str = DEFAULT_COSMOS_CONTAINER,
        client: httpx.Client | None = None,
    ) -> None:
        self.endpoint = endpoint.rstrip("/")
        self.key = key
        self.database = database
        self.container = container
        self._client = client

    def put_json(self, *, session_id: str, digest: str, payload: str) -> None:
        body = {
            "id": digest,
            "session_id": session_id,
            "diagnosis_digest": digest,
            "payload": json.loads(payload),
        }
        self._request(
            "POST",
            f"/dbs/{self.database}/colls/{self.container}/docs",
            resource_type="docs",
            resource_id=f"dbs/{self.database}/colls/{self.container}",
            json_body=body,
            extra_headers={"x-ms-documentdb-is-upsert": "True"},
        )

    def get_json_by_session_id(self, session_id: str) -> str | None:
        return self._query("SELECT * FROM c WHERE c.session_id = @value", session_id)

    def get_json_by_digest(self, digest: str) -> str | None:
        try:
            doc = self._request(
                "GET",
                f"/dbs/{self.database}/colls/{self.container}/docs/{digest}",
                resource_type="docs",
                resource_id=f"dbs/{self.database}/colls/{self.container}/docs/{digest}",
            )
        except DurableWriteError:
            return self._query(
                "SELECT * FROM c WHERE c.diagnosis_digest = @value", digest
            )
        return self._payload_from_doc(doc)

    def _query(self, query: str, value: str) -> str | None:
        doc = self._request(
            "POST",
            f"/dbs/{self.database}/colls/{self.container}/docs",
            resource_type="docs",
            resource_id=f"dbs/{self.database}/colls/{self.container}",
            json_body={
                "query": query,
                "parameters": [{"name": "@value", "value": value}],
            },
            extra_headers={
                "x-ms-documentdb-isquery": "True",
                "Content-Type": "application/query+json",
            },
        )
        documents = doc.get("Documents") if isinstance(doc, dict) else None
        if not documents:
            return None
        return self._payload_from_doc(documents[0])

    def _payload_from_doc(self, doc: dict[str, Any]) -> str | None:
        payload = doc.get("payload")
        if payload is None:
            return None
        if isinstance(payload, str):
            return payload
        return json.dumps(payload)

    def _request(
        self,
        method: str,
        path: str,
        *,
        resource_type: str,
        resource_id: str,
        json_body: dict[str, Any] | None = None,
        extra_headers: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        date = datetime.now(timezone.utc).strftime("%a, %d %b %Y %H:%M:%S GMT")
        headers = {
            "Accept": "application/json",
            "x-ms-date": date,
            "x-ms-version": "2018-12-31",
        }
        if self.key:
            headers["Authorization"] = _cosmos_authorization(
                method, resource_type, resource_id, date, self.key
            )
        if extra_headers:
            headers.update(extra_headers)
        client = self._client or httpx.Client(timeout=10.0)
        owns = self._client is None
        try:
            response = client.request(
                method,
                f"{self.endpoint}{path}",
                headers=headers,
                json=json_body,
            )
        except httpx.HTTPError as exc:
            raise DurableWriteError(f"cosmos request failed: {exc}") from exc
        finally:
            if owns:
                client.close()
        if response.status_code in {404, 204}:
            raise DurableWriteError(f"cosmos miss: {response.status_code}")
        if response.status_code >= 400:
            raise DurableWriteError(
                f"cosmos {response.status_code}: {response.text[:200]}"
            )
        if not response.content:
            return {}
        try:
            payload = response.json()
        except json.JSONDecodeError as exc:
            raise DurableWriteError("cosmos returned a malformed payload") from exc
        if not isinstance(payload, dict):
            raise DurableWriteError("cosmos returned a malformed payload")
        return payload


class BlobDurableBackend:
    """Azure Blob REST. Blobs are named by diagnosis.digest() with a session pointer."""

    def __init__(
        self,
        account_url: str,
        *,
        key: str | None = None,
        container: str = DEFAULT_BLOB_CONTAINER,
        client: httpx.Client | None = None,
    ) -> None:
        self.account_url = account_url.rstrip("/")
        self.key = key
        self.container = container
        self._client = client

    def put_json(self, *, session_id: str, digest: str, payload: str) -> None:
        self._put_blob(f"{digest}.json", payload)
        self._put_blob(f"session/{session_id}.json", digest)

    def get_json_by_session_id(self, session_id: str) -> str | None:
        digest = self._get_blob(f"session/{session_id}.json")
        if digest is None:
            return None
        return self.get_json_by_digest(digest)

    def get_json_by_digest(self, digest: str) -> str | None:
        return self._get_blob(f"{digest}.json")

    def _put_blob(self, name: str, body: str) -> None:
        response = self._call(
            "PUT",
            name,
            content=body.encode("utf-8"),
            headers={"x-ms-blob-type": "BlockBlob", "Content-Type": "application/json"},
        )
        if response.status_code >= 400:
            raise DurableWriteError(
                f"blob write {response.status_code}: {response.text[:200]}"
            )

    def _get_blob(self, name: str) -> str | None:
        response = self._call("GET", name)
        if response.status_code == 404:
            return None
        if response.status_code >= 400:
            raise DurableWriteError(
                f"blob read {response.status_code}: {response.text[:200]}"
            )
        return response.text

    def _call(
        self,
        method: str,
        name: str,
        *,
        content: bytes | None = None,
        headers: dict[str, str] | None = None,
    ) -> httpx.Response:
        url = f"{self.account_url}/{self.container}/{name}"
        date = datetime.now(timezone.utc).strftime("%a, %d %b %Y %H:%M:%S GMT")
        request_headers = {"x-ms-date": date, "x-ms-version": "2020-10-02"}
        if headers:
            request_headers.update(headers)
        if self.key:
            request_headers["Authorization"] = _blob_authorization(
                method, url, request_headers, self.key, content_length=len(content or b"")
            )
        client = self._client or httpx.Client(timeout=10.0)
        owns = self._client is None
        try:
            return client.request(method, url, headers=request_headers, content=content)
        except httpx.HTTPError as exc:
            raise DurableWriteError(f"blob request failed: {exc}") from exc
        finally:
            if owns:
                client.close()


def durable_from_env() -> DurableBackend | None:
    cosmos = _cosmos_from_env()
    blob = _blob_from_env()
    if cosmos is not None and blob is not None:
        return FallbackDurableBackend(cosmos, blob)
    return cosmos or blob


def _cosmos_from_env() -> CosmosDurableBackend | None:
    endpoint = os.environ.get(ENV_COSMOS_ENDPOINT, "").strip()
    if not endpoint:
        return None
    return CosmosDurableBackend(
        endpoint,
        key=os.environ.get(ENV_COSMOS_KEY, "").strip() or None,
        database=os.environ.get(ENV_COSMOS_DATABASE, DEFAULT_COSMOS_DATABASE).strip()
        or DEFAULT_COSMOS_DATABASE,
        container=os.environ.get(ENV_COSMOS_CONTAINER, DEFAULT_COSMOS_CONTAINER).strip()
        or DEFAULT_COSMOS_CONTAINER,
    )


def _blob_from_env() -> BlobDurableBackend | None:
    account_url = os.environ.get(ENV_BLOB_ACCOUNT_URL, "").strip()
    if not account_url:
        return None
    return BlobDurableBackend(
        account_url,
        key=os.environ.get(ENV_BLOB_KEY, "").strip() or None,
        container=os.environ.get(ENV_BLOB_CONTAINER, DEFAULT_BLOB_CONTAINER).strip()
        or DEFAULT_BLOB_CONTAINER,
    )


def _cosmos_authorization(
    verb: str, resource_type: str, resource_id: str, date: str, key: str
) -> str:
    text = (
        f"{verb.lower()}\n{resource_type.lower()}\n{resource_id}\n{date.lower()}\n\n"
    )
    digest = hmac.new(base64.b64decode(key), text.encode("utf-8"), hashlib.sha256).digest()
    signature = base64.b64encode(digest).decode("ascii")
    return quote(f"type=master&ver=1.0&sig={signature}", safe="")


def _blob_authorization(
    method: str,
    url: str,
    headers: dict[str, str],
    key: str,
    *,
    content_length: int,
) -> str:
    parsed = urlparse(url)
    account = parsed.netloc.split(".")[0]
    canonical_headers = "".join(
        f"{name.lower()}:{headers[name]}\n"
        for name in sorted(headers, key=str.lower)
        if name.lower().startswith("x-ms-")
    )
    canonical_resource = f"/{account}{parsed.path}"
    length = str(content_length) if content_length else ""
    content_type = headers.get("Content-Type", "")
    string_to_sign = (
        f"{method}\n\n\n{length}\n\n{content_type}\n\n\n\n\n\n\n"
        f"{canonical_headers}{canonical_resource}"
    )
    digest = hmac.new(
        base64.b64decode(key), string_to_sign.encode("utf-8"), hashlib.sha256
    ).digest()
    signature = base64.b64encode(digest).decode("ascii")
    return f"SharedKey {account}:{signature}"
