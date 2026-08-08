#!/usr/bin/env python3
"""One bounded, host-key-pinned SSH bridge to the wp-hub release facade."""

from __future__ import annotations

import json
import hashlib
import os
import re
import resource
import signal
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

MAX_INPUT_BYTES = 8 * 1024 * 1024
MAX_OUTPUT_BYTES = 8 * 1024 * 1024
SHA256 = re.compile(r"^[0-9a-f]{64}$")
ERROR_CODE = re.compile(r"^[a-z][a-z0-9_]{2,127}$")
HOST = re.compile(
    r"^(?:[a-zA-Z0-9](?:[a-zA-Z0-9.-]{0,251}[a-zA-Z0-9])?"
    r"|\d{1,3}(?:\.\d{1,3}){3})$"
)
USER = re.compile(r"^[a-z_][a-z0-9_-]{0,31}$")
REMOTE_PATH = re.compile(r"^/opt/wp-hub/[a-zA-Z0-9._/-]{1,240}$")
TIMEOUTS = {
    "prepare_isolated_staging": 900,
    "deploy_artifacts": 300,
    "pull_source": 120,
    "stage_targets": 300,
    "collect_acceptance": 900,
    "publish_approved_actions": 900,
    "purge_cache_once": 60,
    "read_public_release": 120,
    "cleanup_isolated_staging": 300,
    "resource_postflight": 120,
    "rollback_target": 300,
}


def canonical_json(value: Any) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def _required_path(
    name: str,
    max_bytes: int,
    *,
    forbidden_mode_bits: int = 0o077,
) -> Path:
    value = os.environ.get(name, "")
    path = Path(value).expanduser()
    if (
        not value
        or not path.is_absolute()
        or not path.is_file()
        or path.stat().st_size < 1
        or path.stat().st_size > max_bytes
        or path.stat().st_mode & forbidden_mode_bits
    ):
        raise ValueError(f"{name.lower()}_invalid")
    return path.resolve()


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _bounded_error_code(raw: bytes) -> str | None:
    """Read only one non-secret error code from a failed JSON boundary."""
    try:
        value = json.loads(raw)
    except (json.JSONDecodeError, UnicodeDecodeError):
        return None
    if not isinstance(value, dict) or set(value) != {
        "success",
        "error_code",
    }:
        return None
    code = value.get("error_code")
    if value.get("success") is not False or not isinstance(code, str):
        return None
    return code if ERROR_CODE.fullmatch(code) else None


def _configuration() -> dict[str, Any]:
    host = os.environ.get("WP_HUB_RELEASE_SSH_HOST", "")
    user = os.environ.get("WP_HUB_RELEASE_SSH_USER", "")
    port_value = os.environ.get("WP_HUB_RELEASE_SSH_PORT", "22")
    remote = os.environ.get("WP_HUB_RELEASE_REMOTE_EXECUTABLE", "")
    remote_sha256 = os.environ.get(
        "WP_HUB_RELEASE_REMOTE_EXECUTABLE_SHA256",
        "",
    )
    try:
        port = int(port_value)
    except ValueError as exc:
        raise ValueError("wp_hub_release_ssh_port_invalid") from exc
    if (
        not HOST.fullmatch(host)
        or not USER.fullmatch(user)
        or not 1 <= port <= 65535
        or not REMOTE_PATH.fullmatch(remote)
        or ".." in Path(remote).parts
        or not SHA256.fullmatch(remote_sha256)
    ):
        raise ValueError("wp_hub_release_ssh_configuration_invalid")
    identity = _required_path(
        "WP_HUB_RELEASE_SSH_IDENTITY_FILE",
        64 * 1024,
    )
    known_hosts = _required_path(
        "WP_HUB_RELEASE_SSH_KNOWN_HOSTS_FILE",
        1024 * 1024,
        forbidden_mode_bits=0o133,
    )
    identity_sha256 = os.environ.get(
        "WP_HUB_RELEASE_SSH_IDENTITY_SHA256",
        "",
    )
    known_hosts_sha256 = os.environ.get(
        "WP_HUB_RELEASE_SSH_KNOWN_HOSTS_SHA256",
        "",
    )
    if (
        not SHA256.fullmatch(identity_sha256)
        or not SHA256.fullmatch(known_hosts_sha256)
        or _sha256(identity) != identity_sha256
        or _sha256(known_hosts) != known_hosts_sha256
    ):
        raise ValueError("wp_hub_release_ssh_identity_pin_invalid")
    return {
        "host": host,
        "user": user,
        "port": port,
        "identity": identity,
        "known_hosts": known_hosts,
        "remote": remote,
        "remote_sha256": remote_sha256,
    }


def _ssh_base(config: dict[str, Any]) -> list[str]:
    return [
        "/usr/bin/ssh",
        "-T",
        "-a",
        "-i",
        str(config["identity"]),
        "-p",
        str(config["port"]),
        "-o",
        "BatchMode=yes",
        "-o",
        "PasswordAuthentication=no",
        "-o",
        "KbdInteractiveAuthentication=no",
        "-o",
        "IdentitiesOnly=yes",
        "-o",
        "StrictHostKeyChecking=yes",
        "-o",
        f"UserKnownHostsFile={config['known_hosts']}",
        "-o",
        "ConnectTimeout=10",
        "-o",
        "ServerAliveInterval=15",
        "-o",
        "ServerAliveCountMax=2",
        "-o",
        "ClearAllForwardings=yes",
        "-o",
        "PermitLocalCommand=no",
        "-o",
        "RequestTTY=no",
        "-o",
        "LogLevel=ERROR",
        f"{config['user']}@{config['host']}",
    ]


def _run(
    command: list[str],
    *,
    timeout: int,
    input_bytes: bytes | None = None,
    output_limit: int,
) -> bytes:
    with tempfile.TemporaryFile() as output:
        process = subprocess.Popen(
            command,
            stdin=(
                subprocess.PIPE
                if input_bytes is not None
                else subprocess.DEVNULL
            ),
            stdout=output,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
            preexec_fn=_limits,
        )
        try:
            process.communicate(input=input_bytes, timeout=timeout)
        except subprocess.TimeoutExpired as exc:
            os.killpg(process.pid, signal.SIGKILL)
            process.wait()
            raise RuntimeError("wp_hub_release_ssh_timeout") from exc
        if output.tell() > output_limit:
            raise RuntimeError("wp_hub_release_ssh_output_too_large")
        output.seek(0)
        value = output.read()
    if process.returncode != 0:
        error_code = _bounded_error_code(value)
        if error_code is not None:
            raise RuntimeError(error_code)
        raise RuntimeError(
            f"wp_hub_release_ssh_failed:{process.returncode}"
        )
    return value


def _limits() -> None:
    resource.setrlimit(
        resource.RLIMIT_FSIZE,
        (MAX_OUTPUT_BYTES, MAX_OUTPUT_BYTES),
    )


def execute(raw: bytes) -> bytes:
    if len(raw) > MAX_INPUT_BYTES:
        raise ValueError("wp_hub_release_bridge_input_too_large")
    envelope = json.loads(raw)
    if not isinstance(envelope, dict):
        raise ValueError("wp_hub_release_bridge_envelope_invalid")
    operation = str(envelope.get("operation") or "")
    timeout = TIMEOUTS.get(operation)
    if timeout is None:
        raise ValueError("wp_hub_release_bridge_operation_invalid")
    config = _configuration()
    base = _ssh_base(config)
    identity = _run(
        [
            *base,
            "/usr/bin/sha256sum",
            config["remote"],
        ],
        timeout=30,
        output_limit=1024,
    ).decode("utf-8").strip()
    fields = identity.split()
    if (
        len(fields) != 2
        or fields[0] != config["remote_sha256"]
        or fields[1] != config["remote"]
    ):
        raise RuntimeError(
            "wp_hub_release_remote_executable_hash_mismatch"
        )
    return _run(
        [*base, config["remote"]],
        timeout=timeout,
        input_bytes=raw,
        output_limit=MAX_OUTPUT_BYTES,
    )


def main() -> int:
    try:
        raw = sys.stdin.buffer.read(MAX_INPUT_BYTES + 1)
        sys.stdout.buffer.write(execute(raw))
        return 0
    except Exception as exc:
        sys.stdout.write(
            canonical_json(
                {
                    "success": False,
                    "error_code": str(exc).split(":", 1)[0],
                }
            )
            + "\n"
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
