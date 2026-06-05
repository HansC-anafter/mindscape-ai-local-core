"""Per-runner claim mode control for drain and pause operations."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from backend.app.services.runner_resources.snapshots import (
    RedisTtlSnapshotStore,
    SyncRedisTtlSnapshotStore,
)

CLAIM_MODE_KEY_PREFIX = "mindscape:runner_claim_mode:v1"
DEFAULT_CLAIM_MODE_TTL_SECONDS = 6 * 60 * 60
MIN_CLAIM_MODE_TTL_SECONDS = 30
MAX_CLAIM_MODE_TTL_SECONDS = 24 * 60 * 60
ACTIVE_MODE = "active"
CLAIM_BLOCKING_MODES = {"drain", "paused"}
ALLOWED_CLAIM_MODES = {ACTIVE_MODE, *CLAIM_BLOCKING_MODES}


@dataclass(frozen=True)
class RunnerClaimControl:
    runner_id: str
    mode: str = ACTIVE_MODE
    reason: str | None = None
    updated_at: str | None = None
    updated_by: str | None = None
    source: str = "default"
    ttl_seconds: int | None = None

    @property
    def claim_enabled(self) -> bool:
        return self.mode == ACTIVE_MODE

    def to_dict(self) -> dict[str, Any]:
        return {
            "runner_id": self.runner_id,
            "mode": self.mode,
            "claim_enabled": self.claim_enabled,
            "reason": self.reason,
            "updated_at": self.updated_at,
            "updated_by": self.updated_by,
            "source": self.source,
            "ttl_seconds": self.ttl_seconds,
        }


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _clean_string(value: Any) -> str | None:
    if value is None:
        return None
    normalized = str(value).strip()
    return normalized or None


def _key_part(value: Any) -> str:
    normalized = "".join(
        char if char.isalnum() or char in {"-", "_", "."} else "_"
        for char in str(value or "").strip()
    ).strip("_")
    return normalized[:160] or "unknown"


def runner_claim_mode_key(runner_id: str) -> str:
    return f"{CLAIM_MODE_KEY_PREFIX}:runner:{_key_part(runner_id)}"


def _normalize_mode(value: Any) -> str:
    mode = str(value or "").strip().lower()
    if mode not in ALLOWED_CLAIM_MODES:
        raise ValueError("invalid_runner_claim_mode")
    return mode


def _normalize_ttl_seconds(value: Any) -> int:
    try:
        parsed = int(value)
    except Exception:
        parsed = DEFAULT_CLAIM_MODE_TTL_SECONDS
    return max(
        MIN_CLAIM_MODE_TTL_SECONDS,
        min(parsed, MAX_CLAIM_MODE_TTL_SECONDS),
    )


def active_runner_claim_control(
    runner_id: str,
    *,
    source: str = "default",
) -> RunnerClaimControl:
    return RunnerClaimControl(
        runner_id=str(runner_id or "").strip(),
        mode=ACTIVE_MODE,
        source=source,
    )


def _control_from_payload(
    runner_id: str,
    payload: dict[str, Any] | None,
) -> RunnerClaimControl:
    if not isinstance(payload, dict):
        return active_runner_claim_control(runner_id)
    mode = str(payload.get("mode") or "").strip().lower()
    if mode not in CLAIM_BLOCKING_MODES:
        return active_runner_claim_control(runner_id)
    return RunnerClaimControl(
        runner_id=str(payload.get("runner_id") or runner_id or "").strip(),
        mode=mode,
        reason=_clean_string(payload.get("reason")),
        updated_at=_clean_string(payload.get("updated_at")),
        updated_by=_clean_string(payload.get("updated_by")),
        source=_clean_string(payload.get("source")) or "redis",
        ttl_seconds=payload.get("ttl_seconds")
        if isinstance(payload.get("ttl_seconds"), int)
        else None,
    )


async def get_runner_claim_control(
    redis_queue: Any,
    *,
    runner_id: str,
) -> RunnerClaimControl:
    normalized_runner_id = str(runner_id or "").strip()
    if not normalized_runner_id:
        return active_runner_claim_control("")
    payload = await RedisTtlSnapshotStore(redis_queue).get(
        runner_claim_mode_key(normalized_runner_id)
    )
    return _control_from_payload(normalized_runner_id, payload)


def get_runner_claim_control_sync(
    runner_id: str,
    *,
    cache_service: Any = None,
) -> RunnerClaimControl:
    normalized_runner_id = str(runner_id or "").strip()
    if not normalized_runner_id:
        return active_runner_claim_control("")
    payload = SyncRedisTtlSnapshotStore(cache_service).get(
        runner_claim_mode_key(normalized_runner_id)
    )
    return _control_from_payload(normalized_runner_id, payload)


def set_runner_claim_mode_sync(
    runner_id: str,
    mode: str,
    *,
    reason: str | None = None,
    updated_by: str | None = None,
    ttl_seconds: int | None = None,
    cache_service: Any = None,
) -> RunnerClaimControl:
    normalized_runner_id = str(runner_id or "").strip()
    if not normalized_runner_id:
        raise ValueError("runner_id_required")
    normalized_mode = _normalize_mode(mode)
    key = runner_claim_mode_key(normalized_runner_id)
    if normalized_mode == ACTIVE_MODE:
        cache = cache_service
        if cache is None:
            from backend.app.services.cache.redis_cache import get_cache_service

            cache = get_cache_service()
        delete_value = getattr(cache, "delete", None)
        if callable(delete_value):
            delete_value(key)
        return active_runner_claim_control(normalized_runner_id, source="cleared")

    normalized_ttl = _normalize_ttl_seconds(ttl_seconds)
    payload = {
        "version": 1,
        "runner_id": normalized_runner_id,
        "mode": normalized_mode,
        "claim_enabled": False,
        "reason": _clean_string(reason) or normalized_mode,
        "updated_at": _utc_now_iso(),
        "updated_by": _clean_string(updated_by),
        "source": "api",
        "ttl_seconds": normalized_ttl,
    }
    ok = SyncRedisTtlSnapshotStore(cache_service).set(
        key,
        payload,
        normalized_ttl,
    )
    if not ok:
        raise RuntimeError("runner_claim_mode_store_unavailable")
    return _control_from_payload(normalized_runner_id, payload)


def runner_claims_enabled(control: RunnerClaimControl | dict[str, Any] | None) -> bool:
    if isinstance(control, RunnerClaimControl):
        return control.claim_enabled
    if isinstance(control, dict):
        mode = str(control.get("mode") or ACTIVE_MODE).strip().lower()
        claim_enabled = control.get("claim_enabled")
        return mode == ACTIVE_MODE and claim_enabled is not False
    return True


async def attach_runner_claim_controls(
    redis_queue: Any,
    heartbeats: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    enriched: list[dict[str, Any]] = []
    for heartbeat in heartbeats:
        if not isinstance(heartbeat, dict):
            continue
        runner_id = str(heartbeat.get("runner_id") or "").strip()
        control = await get_runner_claim_control(redis_queue, runner_id=runner_id)
        enriched.append({**heartbeat, "claim_control": control.to_dict()})
    return enriched
