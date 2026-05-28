"""
Host-side WebSocket client for shared CLI surfaces.

This script runs in the host environment to:
  1. Connect to the Mindscape backend via WebSocket
  2. Authenticate using HMAC challenge-response
  3. Receive dispatched coding tasks
  4. Execute tasks via the surface-specific CLI runtime
  5. Send back ack, progress, and result messages

Usage:
    python host_ws_client.py --workspace-id ws-123 --surface codex_cli
    python host_ws_client.py --workspace-id ws-123 --auth-secret my_secret

Environment Variables:
    MINDSCAPE_WS_HOST       Backend host (default: localhost:8000)
    MINDSCAPE_AUTH_SECRET    HMAC auth secret (optional, skipped in dev mode)
    MINDSCAPE_WORKSPACE_ID  Workspace ID
    MINDSCAPE_SURFACE       Required surface type
    MINDSCAPE_RESULT_ACK_TIMEOUT  Ack wait timeout before REST fallback
    MINDSCAPE_WS_OPEN_TIMEOUT  WebSocket opening handshake timeout
    MINDSCAPE_WS_PONG_TIMEOUT  App-level pong timeout before stale reconnect
"""

import argparse
import asyncio
import base64
import copy
import hashlib
import hmac
import json
import logging
import os
from pathlib import Path
import re
import signal
import sys
import tempfile
import time
from datetime import datetime, timezone
import urllib.error
import urllib.parse
import urllib.request
from collections import OrderedDict
from typing import Any, Callable, Coroutine, Dict, List, Optional, Set

try:
    import websockets
except ImportError:
    print("ERROR: 'websockets' package required. Install with: pip install websockets")
    sys.exit(1)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger("host_ws_client")

UNKNOWN_EXECUTION_ERROR_RE = re.compile(r"Unknown execution ([0-9a-fA-F-]+)")


def _default_client_id(*, workspace_id: str, surface: str) -> str:
    seed = f"{(surface or '').strip().lower()}::{(workspace_id or '').strip()}"
    digest = hashlib.sha1(seed.encode("utf-8")).hexdigest()[:12]
    safe_surface = re.sub(r"[^a-z0-9_.-]+", "-", (surface or "").strip().lower()).strip(
        "-"
    ) or "surface"
    safe_workspace = re.sub(
        r"[^a-zA-Z0-9_.-]+", "-", (workspace_id or "").strip()
    ).strip("-") or "workspace"
    return f"{safe_surface}-{safe_workspace}-{digest}"


def _env_float(name: str, default: float, *, minimum: Optional[float] = None) -> float:
    raw = os.environ.get(name, "").strip()
    if not raw:
        return default
    try:
        value = float(raw)
    except ValueError:
        logger.warning("Invalid %s=%r; falling back to %.1f", name, raw, default)
        return default
    if minimum is not None and value < minimum:
        logger.warning(
            "Invalid %s=%.3f below minimum %.3f; falling back to %.1f",
            name,
            value,
            minimum,
            default,
        )
        return default
    return value


def _env_int(name: str, default: int) -> int:
    raw = os.environ.get(name, "").strip()
    if not raw:
        return default
    try:
        return int(raw)
    except ValueError:
        logger.warning("Invalid %s=%r; falling back to %s", name, raw, default)
        return default


def _env_flag(name: str, default: bool) -> bool:
    raw = os.environ.get(name, "").strip().lower()
    if not raw:
        return default
    if raw in {"1", "true", "yes", "on"}:
        return True
    if raw in {"0", "false", "no", "off"}:
        return False
    logger.warning("Invalid %s=%r; falling back to %s", name, raw, default)
    return default


def _safe_path_component(value: str) -> str:
    cleaned = "".join(
        ch if ch.isalnum() or ch in ("-", "_", ".") else "_"
        for ch in (value or "").strip()
    )
    return cleaned or "unknown"


def _runtime_identity() -> Dict[str, Any]:
    """Collect lightweight host-process identity for signal/debug traces."""
    identity: Dict[str, Any] = {
        "pid": os.getpid(),
        "ppid": os.getppid(),
        "pgid": None,
        "xpc_service_name": os.environ.get("XPC_SERVICE_NAME", ""),
        "workspace_id": os.environ.get("MINDSCAPE_WORKSPACE_ID", ""),
        "surface": os.environ.get("MINDSCAPE_SURFACE", ""),
    }
    try:
        identity["pgid"] = os.getpgid(0)
    except OSError:
        identity["pgid"] = None
    return identity


def _default_backend_api_url(host: str) -> str:
    explicit = os.environ.get("MINDSCAPE_BACKEND_API_URL", "").strip()
    if explicit:
        return explicit.rstrip("/")

    control_host = os.environ.get("MINDSCAPE_CONTROL_PLANE_HOST", "").strip()
    if control_host:
        if control_host.startswith(("http://", "https://")):
            return control_host.rstrip("/")
        return f"http://{control_host}"

    control_port = os.environ.get("MINDSCAPE_CONTROL_PLANE_HOST_PORT", "").strip() or "8220"
    normalized_host = (host or "").strip() or "localhost:8200"
    host_without_scheme = normalized_host.split("://", 1)[-1]

    if host_without_scheme.startswith("[") and "]" in host_without_scheme:
        closing = host_without_scheme.find("]")
        host_name = host_without_scheme[: closing + 1]
    elif ":" in host_without_scheme:
        host_name = host_without_scheme.rsplit(":", 1)[0]
    else:
        host_name = host_without_scheme

    host_name = host_name or "localhost"
    return f"http://{host_name}:{control_port}"


def _format_url_host(host: str, port: Optional[int]) -> str:
    host = (host or "").strip()
    if ":" in host and not host.startswith("["):
        host = f"[{host}]"
    if port is None:
        return host
    return f"{host}:{port}"


def _backend_api_url_candidates(base_url: str) -> List[str]:
    normalized = (base_url or "").strip().rstrip("/")
    if not normalized:
        return []

    parsed = urllib.parse.urlsplit(normalized)
    scheme = parsed.scheme or "http"
    host = (parsed.hostname or "").strip()
    port = parsed.port
    path = parsed.path.rstrip("/")

    hosts: List[str] = []
    if host:
        hosts.append(host)
        if host in {"localhost", "127.0.0.1", "0.0.0.0", "::1"}:
            hosts.extend(["localhost", "127.0.0.1", "0.0.0.0", "host.docker.internal"])

    candidates: List[str] = []
    for candidate_host in hosts:
        candidate = f"{scheme}://{_format_url_host(candidate_host, port)}{path}"
        if candidate not in candidates:
            candidates.append(candidate)

    return candidates or [normalized]

__all__ = [
    "Any",
    "Callable",
    "Coroutine",
    "Dict",
    "List",
    "Optional",
    "OrderedDict",
    "Path",
    "Set",
    "UNKNOWN_EXECUTION_ERROR_RE",
    "argparse",
    "asyncio",
    "base64",
    "copy",
    "datetime",
    "hashlib",
    "hmac",
    "json",
    "logger",
    "logging",
    "os",
    "re",
    "signal",
    "sys",
    "tempfile",
    "time",
    "timezone",
    "urllib",
    "websockets",
    "_backend_api_url_candidates",
    "_default_backend_api_url",
    "_default_client_id",
    "_env_flag",
    "_env_float",
    "_env_int",
    "_format_url_host",
    "_runtime_identity",
    "_safe_path_component",
]
