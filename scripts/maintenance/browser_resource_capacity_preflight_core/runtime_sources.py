"""Lightweight authoritative sources for browser capacity preflight."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .commands import ReadOnlyCommandRunner


BACKEND_APP_MOUNT = "/app/backend"
BACKEND_DATA_MOUNT = "/app/data"
CLAIM_GATE_BOOTSTRAP_RELATIVE_PATH = Path("runtime/runner-claim-gate.paused")

_PLAYBOOK_SPEC_RELATIVE_PATHS = {
    "ig_analyze_following": Path(
        "app/capabilities/ig/playbooks/specs/ig_analyze_following.json"
    ),
    "ig_batch_pin_references": Path(
        "app/capabilities/ig/playbooks/specs/ig_batch_pin_references.json"
    ),
    "ig_pin_post_detail": Path(
        "app/capabilities/ig/playbooks/specs/ig_pin_post_detail.json"
    ),
}

_EXECUTION_PROFILE_KEYS = {
    "resource_class",
    "queue_partition",
    "queue_shard",
    "task_family",
    "managed_runner_role",
    "fairness_lane_key",
    "runner_profile_hint",
    "runtime_affinity",
    "runner_timeout_seconds",
    "resource_requirements",
    "resource_requirement_variants",
    "runner_metadata_variants",
    "trace_runner_heartbeat",
    "no_progress_watchdog",
    "runner_dependencies",
    "dependency_resolver",
}


def parse_container_mounts(raw: str) -> dict[str, Path]:
    payload = json.loads(raw)
    if not isinstance(payload, list):
        raise ValueError("docker mount payload must be a list")
    mounts: dict[str, Path] = {}
    for item in payload:
        if not isinstance(item, dict):
            continue
        destination = str(item.get("Destination") or "").strip()
        source = Path(str(item.get("Source") or "").strip())
        if not destination or not source.is_absolute():
            continue
        mounts[destination] = source
    return mounts


def collect_backend_mounts(
    runner: ReadOnlyCommandRunner,
    container: str,
) -> dict[str, Path]:
    result = runner.run(
        [
            "docker",
            "inspect",
            "--format",
            "{{json .Mounts}}",
            container,
        ]
    )
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or "backend mounts unavailable")
    mounts = parse_container_mounts(result.stdout.strip())
    missing = {
        destination
        for destination in (BACKEND_APP_MOUNT, BACKEND_DATA_MOUNT)
        if destination not in mounts
    }
    if missing:
        raise RuntimeError(
            "required backend mounts unavailable: " + ",".join(sorted(missing))
        )
    return mounts


def _normalize_gate(raw: dict[str, Any], *, source: str) -> dict[str, Any]:
    gate = dict(raw)
    state = str(gate.get("state") or "open").strip().lower()
    gate["state"] = "paused" if state == "paused" else "open"
    gate["source"] = source
    gate["persisted"] = source in {"redis", "bootstrap_file"}
    return gate


def resolve_claim_gate(
    redis_gate: Any,
    bootstrap_path: Path,
) -> dict[str, Any]:
    """Match runner-claim-gate facade precedence without backend imports."""

    if isinstance(redis_gate, dict) and redis_gate:
        return _normalize_gate(redis_gate, source="redis")
    if bootstrap_path.is_file():
        try:
            payload = json.loads(bootstrap_path.read_text(encoding="utf-8") or "{}")
            if not isinstance(payload, dict):
                payload = {}
            paused_at = datetime.fromtimestamp(
                bootstrap_path.stat().st_mtime,
                tz=timezone.utc,
            ).isoformat()
        except Exception:
            payload = {}
            paused_at = datetime.now(timezone.utc).isoformat()
        payload.update(
            {
                "state": "paused",
                "reason": str(payload.get("reason") or "cold_start_bootstrap"),
                "requested_by": str(
                    payload.get("requested_by") or "local_runtime"
                ),
                "paused_at": str(payload.get("paused_at") or paused_at),
                "bootstrap_path": str(bootstrap_path),
            }
        )
        return _normalize_gate(payload, source="bootstrap_file")
    return {
        "state": "open",
        "reason": None,
        "source": "default",
        "persisted": False,
    }


def load_deployed_playbook_metadata(backend_root: Path) -> dict[str, Any]:
    catalog: dict[str, Any] = {}
    for code, relative_path in _PLAYBOOK_SPEC_RELATIVE_PATHS.items():
        spec_path = backend_root / relative_path
        payload = json.loads(spec_path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            raise ValueError(f"playbook spec must be an object: {code}")
        declared_code = str(payload.get("playbook_code") or "").strip()
        if declared_code != code:
            raise ValueError(f"playbook spec code mismatch: {code}")
        execution_profile = payload.get("execution_profile")
        if not isinstance(execution_profile, dict):
            raise ValueError(f"execution profile missing: {code}")
        metadata = {
            key: value
            for key, value in execution_profile.items()
            if key in _EXECUTION_PROFILE_KEYS
        }
        concurrency = payload.get("concurrency")
        if isinstance(concurrency, dict):
            metadata["concurrency"] = concurrency
        metadata["capability_code"] = "ig"
        catalog[code] = metadata
    return catalog


__all__ = [
    "BACKEND_APP_MOUNT",
    "BACKEND_DATA_MOUNT",
    "CLAIM_GATE_BOOTSTRAP_RELATIVE_PATH",
    "collect_backend_mounts",
    "load_deployed_playbook_metadata",
    "parse_container_mounts",
    "resolve_claim_gate",
]
