"""The only Local Core caller for the CRS external-execution endpoint."""

from __future__ import annotations

import json
import os
from pathlib import Path

import httpx

from .external_execution_contracts import (
    ExternalExecutionAuthorizationRequest,
    ExternalExecutionAuthorizationResponse,
    ExternalExecutionDecisionClaims,
)
from .external_execution_verifier import (
    ExternalExecutionDecisionInvalid,
    ExternalExecutionDecisionVerifier,
)


EXTERNAL_AUTHORIZATION_PATH = (
    "/api/v1/crs/external-executions/authorize"
)
MAX_REQUEST_BYTES = 64 * 1024


class ExternalAuthorizationUnavailable(RuntimeError):
    pass


class ExternalAuthorizationDenied(RuntimeError):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


def _read_service_token() -> str:
    token_file = os.getenv("CRS_SERVICE_AUTH_TOKEN_FILE", "").strip()
    if token_file:
        try:
            value = Path(token_file).read_text(encoding="utf-8").strip()
        except OSError:
            value = ""
        if value:
            return value
    return (
        os.getenv("CRS_SERVICE_AUTH_TOKEN")
        or os.getenv("REMOTE_CRS_TOKEN")
        or ""
    ).strip()


class ExternalExecutionAuthorizationAdapter:
    """One bounded, reusable HTTP client with fail-closed semantics."""

    def __init__(
        self,
        *,
        base_url: str | None = None,
        service_token: str | None = None,
        verifier: ExternalExecutionDecisionVerifier | None = None,
        http_client: httpx.AsyncClient | None = None,
    ) -> None:
        self._base_url = (
            base_url
            or os.getenv("CRS_API_URL")
            or os.getenv("REMOTE_CRS_URL")
            or ""
        ).rstrip("/")
        self._service_token = service_token or _read_service_token()
        self._verifier = (
            verifier or ExternalExecutionDecisionVerifier.from_environment()
        )
        self._http_client = http_client
        self._owns_client = http_client is None

    def _client(self) -> httpx.AsyncClient:
        if self._http_client is None:
            if not self._base_url or not self._service_token:
                raise ExternalAuthorizationUnavailable(
                    "external_authorization_unavailable"
                )
            self._http_client = httpx.AsyncClient(
                base_url=self._base_url,
                timeout=httpx.Timeout(
                    timeout=10.0,
                    connect=3.0,
                    pool=2.0,
                ),
                limits=httpx.Limits(
                    max_connections=8,
                    max_keepalive_connections=4,
                ),
            )
        return self._http_client

    async def authorize_root(
        self,
        request: ExternalExecutionAuthorizationRequest,
    ) -> ExternalExecutionDecisionClaims:
        payload = request.model_dump(mode="json")
        encoded = json.dumps(
            payload,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
        if len(encoded) > MAX_REQUEST_BYTES:
            raise ExternalAuthorizationUnavailable(
                "external_authorization_payload_too_large"
            )
        headers = {
            "X-Service-Auth": self._service_token,
            "X-Source-Runtime-ID": request.source_runtime_id,
            "X-Workspace-ID": request.workspace_id,
            "X-Active-Group-ID": request.active_group_id,
        }
        try:
            response = await self._client().post(
                EXTERNAL_AUTHORIZATION_PATH,
                content=encoded,
                headers={
                    **headers,
                    "Content-Type": "application/json",
                },
            )
            response.raise_for_status()
            envelope = ExternalExecutionAuthorizationResponse.model_validate(
                response.json()
            )
            self._verifier.verify(envelope.decision, request=request)
        except (
            httpx.HTTPError,
            ValueError,
            ExternalExecutionDecisionInvalid,
        ) as exc:
            raise ExternalAuthorizationUnavailable(
                "external_authorization_unavailable"
            ) from exc
        claims = envelope.decision.claims
        if not claims.allowed:
            raise ExternalAuthorizationDenied(
                claims.deny_code or "external_authorization_denied"
            )
        return claims

    async def aclose(self) -> None:
        if self._http_client is not None and self._owns_client:
            await self._http_client.aclose()
            self._http_client = None
