#!/usr/bin/env python3
"""Validate the Remote Workbench ingress lock against live connector metrics."""

from __future__ import annotations

import argparse
import base64
import binascii
import hashlib
import json
import os
import re
import stat
import urllib.error
import urllib.request
from dataclasses import asdict, dataclass
from datetime import datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any


LOCK_KEYS = {
    "schema_version",
    "tunnel_id",
    "config_version",
    "config_sha256",
    "config_src",
    "hostname",
    "service",
    "catch_all",
    "verified_at",
}
TOKEN_KEYS = {"a", "s", "t"}
TOKEN_OPTIONAL_KEYS = {"e"}
TUNNEL_ID_PATTERN = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$"
)
SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")
VERIFIED_AT_PATTERN = re.compile(
    r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{6}Z$"
)
METRIC_NAME = "cloudflared_orchestration_config_version"
MAX_METRICS_BYTES = 262_144
CANONICAL_CONFIG = {
    "ingress": [
        {
            "hostname": "remote-workbench.mindscapeai.app",
            "service": "http://mindscape-ai-local-core-frontend:3001",
        },
        {"service": "http_status:404"},
    ],
    "warp-routing": {"enabled": False},
}


class IngressLockError(RuntimeError):
    """Raised when lock or live connector evidence is not conformant."""


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


@dataclass(frozen=True)
class IngressLock:
    """Non-secret Cloudflare API readback projection."""

    schema_version: int
    tunnel_id: str
    config_version: int
    config_sha256: str
    config_src: str
    hostname: str
    service: str
    catch_all: str
    verified_at: str


def canonical_config_sha256() -> str:
    """Hash the one canonical remotely-managed configuration object."""

    encoded = json.dumps(
        CANONICAL_CONFIG,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _read_secure_regular(
    path: Path,
    *,
    expected_mode: int,
    max_bytes: int,
    prefix: str,
    expected_parent_mode: int | None = None,
) -> bytes:
    no_follow = getattr(os, "O_NOFOLLOW", None)
    directory = getattr(os, "O_DIRECTORY", None)
    if not isinstance(no_follow, int) or not isinstance(directory, int):
        raise IngressLockError(f"{prefix}_no_follow_unavailable")
    parent_fd = None
    file_fd = None
    try:
        parent_fd = os.open(
            path.parent,
            os.O_RDONLY | directory | no_follow | getattr(os, "O_CLOEXEC", 0),
        )
        parent_metadata = os.fstat(parent_fd)
        if not stat.S_ISDIR(parent_metadata.st_mode):
            raise IngressLockError(f"{prefix}_parent_not_directory")
        if (
            expected_parent_mode is not None
            and stat.S_IMODE(parent_metadata.st_mode) != expected_parent_mode
        ):
            raise IngressLockError(f"{prefix}_parent_mode_mismatch")
        file_fd = os.open(
            path.name,
            os.O_RDONLY
            | no_follow
            | getattr(os, "O_CLOEXEC", 0)
            | getattr(os, "O_NONBLOCK", 0),
            dir_fd=parent_fd,
        )
        metadata = os.fstat(file_fd)
        if not stat.S_ISREG(metadata.st_mode):
            raise IngressLockError(f"{prefix}_not_regular")
        if stat.S_IMODE(metadata.st_mode) != expected_mode:
            raise IngressLockError(f"{prefix}_mode_mismatch")
        with os.fdopen(file_fd, "rb") as handle:
            file_fd = None
            raw = handle.read(max_bytes + 1)
    except OSError as error:
        raise IngressLockError(f"{prefix}_not_regular") from error
    finally:
        if file_fd is not None:
            os.close(file_fd)
        if parent_fd is not None:
            os.close(parent_fd)
    if len(raw) > max_bytes:
        raise IngressLockError(f"{prefix}_too_large")
    return raw


def _strict_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise IngressLockError("tunnel_token_duplicate_field")
        result[key] = value
    return result


def load_token_tunnel_id(path: Path) -> str:
    """Decode only the non-secret tunnel UUID from one secure Cloudflare token."""

    raw = _read_secure_regular(
        path,
        expected_mode=0o600,
        max_bytes=4096,
        prefix="tunnel_token",
    )
    if not raw:
        raise IngressLockError("tunnel_token_size_mismatch")
    try:
        encoded = raw.decode("ascii").strip()
    except UnicodeDecodeError as error:
        raise IngressLockError("tunnel_token_malformed") from error
    if not encoded or any(character.isspace() for character in encoded):
        raise IngressLockError("tunnel_token_malformed")
    try:
        decoded = base64.b64decode(encoded, validate=True)
        payload: Any = json.loads(decoded, object_pairs_hook=_strict_object)
    except IngressLockError:
        raise
    except (binascii.Error, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise IngressLockError("tunnel_token_malformed") from error
    if not isinstance(payload, dict):
        raise IngressLockError("tunnel_token_schema_mismatch")
    keys = set(payload)
    if not TOKEN_KEYS.issubset(keys) or not keys <= TOKEN_KEYS | TOKEN_OPTIONAL_KEYS:
        raise IngressLockError("tunnel_token_schema_mismatch")
    account = payload["a"]
    secret = payload["s"]
    tunnel_id = payload["t"]
    endpoint = payload.get("e")
    if (
        not isinstance(account, str)
        or not 1 <= len(account) <= 512
        or not isinstance(secret, str)
        or not 1 <= len(secret) <= 4096
        or not isinstance(tunnel_id, str)
        or not TUNNEL_ID_PATTERN.fullmatch(tunnel_id)
        or (
            endpoint is not None
            and (not isinstance(endpoint, str) or not 1 <= len(endpoint) <= 2048)
        )
    ):
        raise IngressLockError("tunnel_token_schema_mismatch")
    try:
        secret_bytes = base64.b64decode(secret, validate=True)
    except binascii.Error as error:
        raise IngressLockError("tunnel_token_schema_mismatch") from error
    if not secret_bytes:
        raise IngressLockError("tunnel_token_schema_mismatch")
    return tunnel_id


def verify_token_identity(lock: IngressLock, token_path: Path) -> str:
    """Bind the mounted token to the exact Cloudflare API tunnel lock."""

    tunnel_id = load_token_tunnel_id(token_path)
    if tunnel_id != lock.tunnel_id:
        raise IngressLockError("tunnel_token_identity_mismatch")
    return tunnel_id


def load_lock(path: Path) -> IngressLock:
    """Read an exact, operator-only ingress lock without accepting aliases."""

    raw = _read_secure_regular(
        path,
        expected_mode=0o600,
        max_bytes=4096,
        prefix="ingress_lock",
        expected_parent_mode=0o700,
    )
    try:
        payload: Any = json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise IngressLockError("ingress_lock_malformed") from error
    if not isinstance(payload, dict) or set(payload) != LOCK_KEYS:
        raise IngressLockError("ingress_lock_schema_mismatch")
    if type(payload["schema_version"]) is not int or payload["schema_version"] != 1:
        raise IngressLockError("ingress_lock_schema_version_mismatch")
    tunnel_id = payload["tunnel_id"]
    if not isinstance(tunnel_id, str) or not TUNNEL_ID_PATTERN.fullmatch(tunnel_id):
        raise IngressLockError("ingress_lock_tunnel_id_malformed")
    config_version = payload["config_version"]
    if type(config_version) is not int or not 0 <= config_version <= 2_147_483_647:
        raise IngressLockError("ingress_lock_config_version_malformed")
    config_hash = payload["config_sha256"]
    if not isinstance(config_hash, str) or not SHA256_PATTERN.fullmatch(config_hash):
        raise IngressLockError("ingress_lock_config_hash_malformed")
    if config_hash != canonical_config_sha256():
        raise IngressLockError("ingress_lock_config_hash_mismatch")
    if (
        payload["config_src"] != "cloudflare"
        or payload["hostname"] != CANONICAL_CONFIG["ingress"][0]["hostname"]
        or payload["service"] != CANONICAL_CONFIG["ingress"][0]["service"]
        or payload["catch_all"] != CANONICAL_CONFIG["ingress"][1]["service"]
    ):
        raise IngressLockError("ingress_lock_topology_mismatch")
    verified_at = payload["verified_at"]
    if not isinstance(verified_at, str) or not VERIFIED_AT_PATTERN.fullmatch(verified_at):
        raise IngressLockError("ingress_lock_verified_at_malformed")
    try:
        datetime.fromisoformat(verified_at[:-1] + "+00:00")
    except ValueError as error:
        raise IngressLockError("ingress_lock_verified_at_malformed") from error
    return IngressLock(
        1,
        tunnel_id,
        config_version,
        config_hash,
        "cloudflare",
        CANONICAL_CONFIG["ingress"][0]["hostname"],
        CANONICAL_CONFIG["ingress"][0]["service"],
        CANONICAL_CONFIG["ingress"][1]["service"],
        verified_at,
    )


def parse_live_config_version(metrics: bytes) -> int:
    """Extract one exact unlabelled config-version gauge sample."""

    if len(metrics) > MAX_METRICS_BYTES:
        raise IngressLockError("connector_metrics_too_large")
    try:
        lines = metrics.decode("utf-8").splitlines()
    except UnicodeDecodeError as error:
        raise IngressLockError("connector_metrics_malformed") from error
    samples = []
    for line in lines:
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        fields = stripped.split()
        if fields and fields[0].split("{", 1)[0] == METRIC_NAME:
            samples.append(fields)
    if len(samples) != 1 or len(samples[0]) != 2 or samples[0][0] != METRIC_NAME:
        raise IngressLockError("connector_config_version_metric_mismatch")
    try:
        value = Decimal(samples[0][1])
    except InvalidOperation as error:
        raise IngressLockError("connector_config_version_metric_malformed") from error
    if not value.is_finite() or value != value.to_integral_value():
        raise IngressLockError("connector_config_version_metric_malformed")
    version = int(value)
    if not 0 <= version <= 2_147_483_647:
        raise IngressLockError("connector_config_version_metric_malformed")
    return version


def read_metrics(url: str, *, timeout_seconds: float = 3.0) -> bytes:
    """Read one bounded loopback-only metrics response."""

    if url != "http://127.0.0.1:2000/metrics":
        raise IngressLockError("connector_metrics_url_mismatch")
    request = urllib.request.Request(url, method="GET")
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), _NoRedirect())
    try:
        with opener.open(request, timeout=timeout_seconds) as response:
            if response.status != 200:
                raise IngressLockError("connector_metrics_http_status")
            body = response.read(MAX_METRICS_BYTES + 1)
    except IngressLockError:
        raise
    except (urllib.error.URLError, TimeoutError, OSError) as error:
        raise IngressLockError("connector_metrics_unavailable") from error
    if len(body) > MAX_METRICS_BYTES:
        raise IngressLockError("connector_metrics_too_large")
    return body


def live_projection(
    lock: IngressLock,
    metric_version: int,
) -> dict[str, Any]:
    """Require the active connector version to match the API readback lock."""

    if metric_version != lock.config_version:
        raise IngressLockError("connector_config_version_drift")
    result = asdict(lock)
    result.update(
        {
            "metric": METRIC_NAME,
            "metric_version": metric_version,
            "remote_ingress_verified": True,
        }
    )
    return result


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=("validate-lock", "verify-live"))
    parser.add_argument("--lock-path", type=Path, required=True)
    parser.add_argument("--token-path", type=Path, required=True)
    parser.add_argument("--metrics-url", default="http://127.0.0.1:2000/metrics")
    parser.add_argument("--json", action="store_true")
    return parser


def main() -> int:
    args = _parser().parse_args()
    try:
        lock = load_lock(args.lock_path)
        verify_token_identity(lock, args.token_path)
        if args.action == "validate-lock":
            payload = {
                **asdict(lock),
                "lock_valid": True,
                "token_tunnel_id_verified": True,
            }
        else:
            metrics = read_metrics(args.metrics_url)
            version = parse_live_config_version(metrics)
            payload = live_projection(lock, version)
    except IngressLockError as error:
        print(str(error), file=os.sys.stderr)
        return 1
    if args.json:
        print(json.dumps(payload, sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
