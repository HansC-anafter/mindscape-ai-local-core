"""Durable state transitions behind the runner claim-gate facade."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from .manager_core import normalize_runner_claim_gate
from .runner_claim_gate_bootstrap import (
    MANAGED_BOOTSTRAP_OWNER,
    clear_managed_runner_claim_gate_bootstrap,
    read_runner_claim_gate_bootstrap,
    write_managed_runner_claim_gate_bootstrap,
)

RUNNER_CLAIM_GATE_KEY = "mindscape:host_resources:runner_claim_gate"


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _read(cache_service: Any) -> dict[str, Any]:
    try:
        value = cache_service.get_json(RUNNER_CLAIM_GATE_KEY)
    except Exception:
        value = None
    return value if isinstance(value, dict) else {}


def _write(cache_service: Any, value: dict[str, Any], ttl_seconds: int) -> bool:
    try:
        return bool(
            cache_service.set_json(
                RUNNER_CLAIM_GATE_KEY,
                value,
                ttl=ttl_seconds,
            )
        )
    except Exception:
        return False


def _delete(cache_service: Any) -> bool:
    try:
        return bool(cache_service.delete(RUNNER_CLAIM_GATE_KEY))
    except Exception:
        return False


def get_claim_gate_state(
    cache_service: Any,
) -> tuple[dict[str, Any] | None, dict[str, Any]]:
    persisted = _read(cache_service)
    if persisted:
        state = normalize_runner_claim_gate(persisted, source="redis")
        return state, dict(state)
    bootstrap = read_runner_claim_gate_bootstrap()
    if bootstrap:
        state = normalize_runner_claim_gate(bootstrap, source="bootstrap_file")
        state["persisted"] = True
        return state, dict(state)
    return None, normalize_runner_claim_gate(None, source="default")


def pause_claim_gate_state(
    cache_service: Any,
    payload: dict[str, Any] | None,
    *,
    default_ttl_seconds: int,
) -> tuple[dict[str, Any], dict[str, Any]]:
    source = payload if isinstance(payload, dict) else {}
    try:
        ttl_seconds = int(source.get("ttl_seconds") or default_ttl_seconds)
    except Exception:
        ttl_seconds = default_ttl_seconds
    ttl_seconds = max(60, ttl_seconds)
    gate = {
        "state": "paused",
        "reason": str(source.get("reason") or "maintenance"),
        "requested_by": str(source.get("requested_by") or "local_runtime"),
        "paused_at": _utc_now_iso(),
        "ttl_seconds": ttl_seconds,
    }
    durable = write_managed_runner_claim_gate_bootstrap(gate)
    persisted = _write(cache_service, gate, ttl_seconds)
    state = dict(gate)
    result = normalize_runner_claim_gate(
        gate,
        source="redis" if persisted else "memory",
    )
    result["persisted"] = persisted
    result["durable"] = durable
    if not durable:
        result["pause_warning"] = "claim_gate_bootstrap_write_failed"
    return state, result


def resume_claim_gate_state(
    cache_service: Any,
) -> tuple[dict[str, Any], dict[str, Any]]:
    bootstrap = read_runner_claim_gate_bootstrap()
    if bootstrap and bootstrap.get("managed_by") != MANAGED_BOOTSTRAP_OWNER:
        state = normalize_runner_claim_gate(bootstrap, source="bootstrap_file")
        state["persisted"] = True
        state["resume_blocked_reason"] = "claim_gate_bootstrap_file_present"
        return state, dict(state)
    if not _delete(cache_service):
        gate = bootstrap or {
            "state": "paused",
            "reason": "claim_gate_redis_delete_failed",
            "requested_by": "local_runtime",
            "paused_at": _utc_now_iso(),
        }
        state = normalize_runner_claim_gate(
            gate,
            source="bootstrap_file" if bootstrap else "memory",
        )
        state["persisted"] = bool(bootstrap)
        state["resume_blocked_reason"] = "claim_gate_redis_delete_failed"
        return state, dict(state)
    if bootstrap:
        cleared, blocked_reason = clear_managed_runner_claim_gate_bootstrap()
        if not cleared:
            state = normalize_runner_claim_gate(
                bootstrap,
                source="bootstrap_file",
            )
            state["persisted"] = True
            state["resume_blocked_reason"] = blocked_reason
            return state, dict(state)
    state = {
        "state": "open",
        "reason": None,
        "resumed_at": _utc_now_iso(),
    }
    result = normalize_runner_claim_gate(state, source="memory")
    result["persisted"] = True
    result["durable"] = True
    return state, result
