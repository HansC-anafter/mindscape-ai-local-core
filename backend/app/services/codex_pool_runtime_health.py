"""Codex pool runtime health summary."""

from __future__ import annotations

import asyncio
from collections import Counter
from datetime import datetime, timezone
from typing import Any


def summarize_codex_pool_runtime_health_sync() -> dict[str, Any]:
    from backend.app.services.codex_pool_health import (
        coerce_datetime,
        is_executable_runtime_metadata,
        read_probe_metadata,
        read_health_metadata,
    )
    from backend.app.services.codex_pool_service import CODEX_POOL_GROUP, CodexPoolService

    service = CodexPoolService()
    db = service._get_db()
    RuntimeEnvironment = service._get_model()
    now = datetime.now(timezone.utc)
    try:
        runtimes = (
            db.query(RuntimeEnvironment)
            .filter(
                RuntimeEnvironment.pool_group == CODEX_POOL_GROUP,
                RuntimeEnvironment.pool_enabled.is_(True),
            )
            .all()
        )

        state_counts: Counter[str] = Counter()
        probe_state_counts: Counter[str] = Counter()
        failure_counts: Counter[str] = Counter()
        active_cooldowns: list[dict[str, Any]] = []
        manual_repair_runtime_ids: list[str] = []
        runnable_runtime_ids: list[str] = []
        runtime_identities: list[dict[str, Any]] = []
        identity_missing_runtime_ids: list[str] = []
        auth_failure_codes = {
            "401",
            "403",
            "auth_failure",
            "deactivated_workspace",
            "stale_refresh_token",
            "unauthorized",
        }

        for runtime in runtimes:
            runtime_id = str(getattr(runtime, "id", "") or "").strip()
            auth_type = str(getattr(runtime, "auth_type", "") or "").strip()
            metadata = dict(getattr(runtime, "extra_metadata", None) or {})
            health = read_health_metadata(metadata, auth_type=auth_type)
            probe = read_probe_metadata(metadata)
            health_state = str(health.get("health_state") or "healthy").strip().lower()
            probe_state = str(probe.get("probe_state") or "unknown").strip().lower()
            executable_seed = is_executable_runtime_metadata(metadata, auth_type=auth_type)
            failure_code = str(
                health.get("last_failure_code")
                or getattr(runtime, "last_error_code", "")
                or ""
            ).strip()
            cooldown_until = coerce_datetime(getattr(runtime, "cooldown_until", None))
            cooldown_active = bool(cooldown_until and cooldown_until > now)
            identity = CodexPoolService._runtime_account_identity_payload(metadata)
            runtime_identity = {
                "runtime_id": runtime_id,
                "metadata_health_state": health_state,
                "probe_state": probe_state,
                "last_probe_success_at": probe.get("last_probe_success_at"),
                **identity,
            }
            runtime_identities.append(runtime_identity)
            if identity.get("identity_status") != "email_verified":
                identity_missing_runtime_ids.append(runtime_id)

            state_counts[health_state] += 1
            probe_state_counts[probe_state] += 1
            if failure_code:
                failure_counts[failure_code] += 1
            if cooldown_active and cooldown_until:
                active_cooldowns.append(
                    {
                        "runtime_id": runtime_id,
                        "last_error_code": failure_code or None,
                        "cooldown_until": cooldown_until.astimezone(
                            timezone.utc
                        ).isoformat(),
                    }
                )
            if (
                health_state == "quarantined"
                and failure_code in auth_failure_codes
                and not cooldown_active
            ):
                manual_repair_runtime_ids.append(runtime_id)
            if executable_seed and health_state in {"healthy", "probation"} and not cooldown_active:
                runnable_runtime_ids.append(runtime_id)

        next_cooldown_until = None
        if active_cooldowns:
            next_cooldown_until = min(
                str(item.get("cooldown_until") or "") for item in active_cooldowns
            )

        return {
            "checked_at": now.isoformat(),
            "pool_enabled_runtime_count": len(runtimes),
            "state_counts": dict(state_counts),
            "probe_state_counts": dict(probe_state_counts),
            "failure_counts": dict(failure_counts),
            "probe_available_runtime_count": int(probe_state_counts.get("available", 0)),
            "runnable_runtime_count": len(runnable_runtime_ids),
            "runnable_runtime_ids": runnable_runtime_ids,
            "active_cooldown_count": len(active_cooldowns),
            "active_cooldowns": sorted(
                active_cooldowns,
                key=lambda item: (
                    str(item.get("cooldown_until") or ""),
                    str(item.get("runtime_id") or ""),
                ),
            ),
            "next_cooldown_until": next_cooldown_until,
            "manual_repair_required_count": len(manual_repair_runtime_ids),
            "manual_repair_runtime_ids": sorted(manual_repair_runtime_ids),
            "identity_missing_count": len(identity_missing_runtime_ids),
            "identity_missing_runtime_ids": sorted(identity_missing_runtime_ids),
            "runtime_identities": sorted(
                runtime_identities,
                key=lambda item: str(item.get("runtime_id") or ""),
            ),
        }
    finally:
        db.close()


async def summarize_codex_pool_runtime_health() -> dict[str, Any]:
    return await asyncio.to_thread(summarize_codex_pool_runtime_health_sync)
