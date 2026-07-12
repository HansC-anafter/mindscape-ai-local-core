"""One-shot Cloudflare remotely-managed ingress readback and apply gate."""

from __future__ import annotations

import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Mapping

from .edge import PUBLIC_HOSTNAME
from .http import HttpClient
from .io import (
    CutoverError,
    assert_private_file,
    write_private_json,
)
from .secure_inputs import SecureInputs


INTERNAL_REMOTE_SERVICE = "http://mindscape-ai-local-core-frontend:3001"
FALLBACK_SERVICE = "http_status:404"
CANONICAL_INGRESS = [
    {"hostname": PUBLIC_HOSTNAME, "service": INTERNAL_REMOTE_SERVICE},
    {"service": FALLBACK_SERVICE},
]
CANONICAL_CONFIG = {
    "ingress": CANONICAL_INGRESS,
    "warp-routing": {"enabled": False},
}


def canonical_config_sha256() -> str:
    """Hash the exact full remotely-managed config shared with the launcher."""

    encoded = json.dumps(
        CANONICAL_CONFIG,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


class RemoteIngressGate:
    """Read and update only the remote Cloudflare configuration source."""

    def __init__(
        self,
        http: HttpClient,
        *,
        now: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
    ) -> None:
        self.http = http
        self.now = now

    @staticmethod
    def _token(inputs: SecureInputs) -> str:
        path = inputs.cloudflare_api_token_path
        if path is None:
            raise CutoverError("Cloudflare API token path is unavailable")
        assert_private_file(path, max_bytes=4_096)
        token = path.read_text(encoding="utf-8").strip()
        if len(token) < 20 or any(character.isspace() for character in token):
            raise CutoverError("Cloudflare API token is malformed")
        return token

    @staticmethod
    def _base_url(inputs: SecureInputs) -> str:
        if not inputs.cloudflare_account_id or not inputs.cloudflare_tunnel_id:
            raise CutoverError("Cloudflare account or tunnel id is unavailable")
        return (
            "https://api.cloudflare.com/client/v4/accounts/"
            f"{inputs.cloudflare_account_id}/cfd_tunnel/{inputs.cloudflare_tunnel_id}"
        )

    def _request(
        self,
        inputs: SecureInputs,
        path: str,
        *,
        method: str = "GET",
        payload: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        response = self.http.request(
            method,
            f"{self._base_url(inputs)}{path}",
            payload=payload,
            headers={"Authorization": f"Bearer {self._token(inputs)}"},
            timeout_seconds=10.0,
            max_response_bytes=65_536,
        )
        if not 200 <= response.status < 300:
            raise CutoverError(f"Cloudflare API returned status {response.status}")
        envelope = response.json()
        result = envelope.get("result")
        if envelope.get("success") is not True or not isinstance(result, dict):
            raise CutoverError("Cloudflare API response is malformed")
        return result

    @staticmethod
    def _version(result: Mapping[str, Any]) -> int:
        value = result.get("version")
        if type(value) is not int or not 0 <= value <= 2_147_483_647:
            raise CutoverError("Cloudflare ingress configuration version is invalid")
        return value

    @staticmethod
    def _normalized_ingress(result: Mapping[str, Any]) -> list[dict[str, str]]:
        config = result.get("config")
        if not isinstance(config, Mapping):
            raise CutoverError("Cloudflare tunnel configuration is missing")
        ingress = config.get("ingress")
        if not isinstance(ingress, list) or not 1 <= len(ingress) <= 32:
            raise CutoverError("Cloudflare ingress rules are malformed")
        normalized: list[dict[str, str]] = []
        for item in ingress:
            if not isinstance(item, Mapping):
                raise CutoverError("Cloudflare ingress rule is malformed")
            hostname = item.get("hostname")
            service = item.get("service")
            path = item.get("path")
            if (
                not isinstance(service, str)
                or not service
                or len(service) > 1_024
                or (hostname is not None and not isinstance(hostname, str))
                or (path is not None and not isinstance(path, str))
            ):
                raise CutoverError("Cloudflare ingress rule values are malformed")
            row = {"service": service}
            if hostname:
                row["hostname"] = hostname
            if path:
                row["path"] = path
            normalized.append(row)
        return normalized

    def capture_prechange(
        self,
        inputs: SecureInputs,
    ) -> dict[str, Any]:
        """Prove remote management and persist a redacted prechange snapshot."""

        metadata = self._request(inputs, "")
        if (
            metadata.get("id") != inputs.cloudflare_tunnel_id
            or metadata.get("account_tag") != inputs.cloudflare_account_id
            or metadata.get("config_src") != "cloudflare"
        ):
            raise CutoverError("Cloudflare tunnel is not the locked remotely-managed tunnel")
        configuration = self._request(inputs, "/configurations")
        version = self._version(configuration)
        ingress = self._normalized_ingress(configuration)
        evidence = {
            "account_id": inputs.cloudflare_account_id,
            "tunnel_id": inputs.cloudflare_tunnel_id,
            "config_src": "cloudflare",
            "config_version": version,
            "ingress": ingress,
            "canonical_config_sha256": canonical_config_sha256(),
        }
        write_private_json(
            inputs.directory / "cloudflare-ingress-before.json",
            evidence,
        )
        return evidence

    def _require_exact_readback(
        self,
        inputs: SecureInputs,
        result: Mapping[str, Any],
    ) -> int:
        if (
            result.get("account_id") != inputs.cloudflare_account_id
            or result.get("tunnel_id") != inputs.cloudflare_tunnel_id
        ):
            raise CutoverError("Cloudflare configuration identity mismatch")
        config = result.get("config")
        if not isinstance(config, Mapping) or dict(config) != CANONICAL_CONFIG:
            raise CutoverError("Cloudflare ingress readback does not match the canonical config")
        return self._version(result)

    def apply_exact(self, inputs: SecureInputs) -> dict[str, Any]:
        """PUT the canonical config once, GET exact readback, then write the lock."""

        updated = self._request(
            inputs,
            "/configurations",
            method="PUT",
            payload={"config": CANONICAL_CONFIG},
        )
        updated_version = self._require_exact_readback(inputs, updated)
        readback = self._request(inputs, "/configurations")
        readback_version = self._require_exact_readback(inputs, readback)
        if readback_version != updated_version:
            raise CutoverError("Cloudflare ingress PUT and GET versions do not match")
        verified_at = self.now().astimezone(timezone.utc).strftime(
            "%Y-%m-%dT%H:%M:%S.%fZ"
        )
        lock = {
            "schema_version": 1,
            "tunnel_id": inputs.cloudflare_tunnel_id,
            "config_version": readback_version,
            "config_sha256": canonical_config_sha256(),
            "config_src": "cloudflare",
            "hostname": PUBLIC_HOSTNAME,
            "service": INTERNAL_REMOTE_SERVICE,
            "catch_all": FALLBACK_SERVICE,
            "verified_at": verified_at,
        }
        state_root = Path(
            os.getenv(
                "REMOTE_WORKBENCH_BRIDGE_STATE_DIR",
                "~/.mindscape/remote-workbench-bridge",
            )
        ).expanduser()
        lock_path = state_root / "remote-ingress-lock.json"
        if state_root.is_symlink() or lock_path.is_symlink():
            raise CutoverError("Remote ingress lock path must not be symbolic")
        write_private_json(lock_path, lock)
        write_private_json(inputs.directory / "cloudflare-ingress-after.json", lock)
        return lock
