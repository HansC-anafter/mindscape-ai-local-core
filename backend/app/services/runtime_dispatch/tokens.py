"""Deterministic token helpers for runtime dispatch previews and applies."""

from __future__ import annotations

import hashlib
import json
from typing import Any


def canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)


def hash_payload(value: Any) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def build_apply_token_digest(
    *,
    selector: dict[str, Any],
    target: dict[str, Any],
    eligible_task_ids: list[str],
    route_snapshots: list[dict[str, Any]],
    actor_id: str,
    workspace_id: str,
    created_at: str,
    expires_at: str,
) -> str:
    payload = {
        "selector_hash": hash_payload(selector),
        "target_hash": hash_payload(target),
        "eligible_task_ids_hash": hash_payload(sorted(eligible_task_ids)),
        "route_snapshots_hash": hash_payload(route_snapshots),
        "actor_id": actor_id,
        "workspace_id": workspace_id,
        "created_at": created_at,
        "expires_at": expires_at,
    }
    return hash_payload(payload)


def build_apply_idempotency_key(plan_id: str, apply_token: str) -> str:
    return hash_payload(
        {
            "plan_id": plan_id,
            "apply_token": apply_token,
        }
    )
