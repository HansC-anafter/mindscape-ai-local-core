"""Shared Codex pool runtime resolver for workspace-bound execution."""

from __future__ import annotations

import asyncio
import logging
from collections import Counter
from datetime import datetime, timezone
from typing import Any, Optional

logger = logging.getLogger(__name__)


def resolve_codex_pool_runtime_bundle_sync(
    *,
    workspace_id: str,
    auth_workspace_id: Optional[str] = None,
    source_workspace_id: Optional[str] = None,
    lease_owner_type: Optional[str] = None,
    lease_owner_id: Optional[str] = None,
    excluded_runtime_ids: Optional[set[str]] = None,
    excluded_quota_scope_keys: Optional[set[str]] = None,
    require_probe_available: bool = False,
    fail_closed_session_lease: bool = True,
    record_runtime_lease: bool = False,
) -> dict[str, Any]:
    from backend.app.services.codex_pool_admission_service import (
        CodexPoolAdmissionService,
    )
    from backend.app.services.codex_pool_service import CodexPoolService
    from backend.app.services.executor_binding_service import ExecutorBindingService
    from backend.app.services.executor_route_resolver import ExecutorRouteResolver

    normalized_workspace_id = str(workspace_id or "").strip()
    normalized_lease_owner_type = str(lease_owner_type or "").strip()
    normalized_lease_owner_id = str(lease_owner_id or "").strip()
    normalized_excluded_runtime_ids = {
        str(runtime_id).strip()
        for runtime_id in (excluded_runtime_ids or set())
        if str(runtime_id).strip()
    }
    normalized_excluded_quota_scope_keys = {
        str(scope_key).strip()
        for scope_key in (excluded_quota_scope_keys or set())
        if str(scope_key).strip()
    }
    selection = None
    if normalized_workspace_id:
        try:
            selection = ExecutorRouteResolver().resolve(
                surface="codex_cli",
                workspace_id=normalized_workspace_id,
                auth_workspace_id=auth_workspace_id,
                source_workspace_id=source_workspace_id,
            )
        except ValueError:
            logger.debug(
                "Workspace-scoped Codex route is not configured for %s",
                normalized_workspace_id,
            )

    binding_service = ExecutorBindingService()
    preference = (
        binding_service.resolve_pool_preference(
            selection=selection,
            lease_owner_type=normalized_lease_owner_type or None,
            lease_owner_id=normalized_lease_owner_id or None,
        )
        if selection
        else {
            "preferred_runtime_id": None,
            "allow_runtime_substitution": False,
            "preference_source": "no_bound_runtime",
            "binding_runtime_id": None,
            "binding_state": None,
            "lease_runtime_id": None,
            "lease_state": None,
        }
    )

    preferred_runtime_id = preference.get("preferred_runtime_id")
    allow_runtime_substitution = bool(
        preference.get("allow_runtime_substitution", preference.get("allow_fallback", False))
    )
    preference_source = str(preference.get("preference_source") or "no_bound_runtime")
    admission = CodexPoolAdmissionService().evaluate_execution_admission(
        preferred_runtime_id=preferred_runtime_id,
        allow_runtime_substitution=allow_runtime_substitution,
        require_probe_available=require_probe_available,
    )
    if not admission.admissible:
        if (
            preference_source == "session_lease"
            and selection
            and normalized_workspace_id
            and normalized_lease_owner_type
            and normalized_lease_owner_id
        ):
            try:
                binding_service.clear_runtime_lease(
                    workspace_id=normalized_workspace_id,
                    surface=selection.surface,
                    lease_owner_type=normalized_lease_owner_type,
                    lease_owner_id=normalized_lease_owner_id,
                    runtime_id=preferred_runtime_id,
                    reason=f"admission:{admission.reason}",
                )
            except Exception:
                logger.warning(
                    "Failed to clear stale Codex runtime lease for workspace %s",
                    normalized_workspace_id,
                    exc_info=True,
                )
        return {
            "error": admission.blocker_message(),
            "admission": admission.to_payload(),
            "preferred_runtime_id": preferred_runtime_id,
            "binding_runtime_id": preference.get("binding_runtime_id"),
            "binding_state": preference.get("binding_state"),
            "preference_source": preference_source,
            "policy_mode": selection.policy_mode if selection else None,
            "requested_workspace_id": (
                selection.requested_workspace_id if selection else normalized_workspace_id or None
            ),
            "effective_workspace_id": selection.effective_workspace_id if selection else None,
            "auth_workspace_id": selection.auth_workspace_id if selection else None,
            "source_workspace_id": selection.source_workspace_id if selection else None,
            "selection_reason": selection.selection_reason if selection else None,
            "selection_trace": list(selection.trace) if selection else [],
        }

    pool_result = CodexPoolService().get_active_auth_bundle(
        preferred_runtime_id=preferred_runtime_id,
        allow_runtime_substitution=allow_runtime_substitution,
        excluded_runtime_ids=normalized_excluded_runtime_ids,
        excluded_quota_scope_keys=normalized_excluded_quota_scope_keys,
        require_probe_available=require_probe_available,
    )
    if (
        "env" not in pool_result
        and pool_result.get("error")
        and preferred_runtime_id
        and preference_source == "binding_snapshot"
    ):
        preferred_runtime_id = None
        allow_runtime_substitution = True
        preference_source = "binding_rebind"
        pool_result = CodexPoolService().get_active_auth_bundle(
            preferred_runtime_id=None,
            allow_runtime_substitution=True,
            excluded_runtime_ids=normalized_excluded_runtime_ids,
            excluded_quota_scope_keys=normalized_excluded_quota_scope_keys,
            require_probe_available=require_probe_available,
        )
    if "env" in pool_result:
        selected_runtime_id = str(pool_result.get("selected_runtime_id") or "").strip()
        selected_quota_scope_key = str(pool_result.get("quota_scope_key") or "").strip()
        if selected_runtime_id and selected_runtime_id in normalized_excluded_runtime_ids:
            return {
                "error": (
                    "pool_reused_excluded_runtime: Codex pool resolver returned "
                    f"excluded runtime {selected_runtime_id}"
                ),
                "selected_runtime_id": selected_runtime_id,
                "excluded_runtime_ids": sorted(normalized_excluded_runtime_ids),
            }
        if (
            selected_quota_scope_key
            and selected_quota_scope_key in normalized_excluded_quota_scope_keys
        ):
            return {
                "error": (
                    "pool_reused_excluded_quota_scope: Codex pool resolver returned "
                    f"excluded quota scope {selected_quota_scope_key}"
                ),
                "selected_runtime_id": selected_runtime_id or None,
                "quota_scope_key": selected_quota_scope_key,
                "excluded_quota_scope_keys": sorted(normalized_excluded_quota_scope_keys),
            }
    if (
        fail_closed_session_lease
        and "env" in pool_result
        and preference_source == "session_lease"
    ):
        selected_runtime_id = str(pool_result.get("selected_runtime_id") or "").strip()
        if (
            selected_runtime_id
            and preferred_runtime_id
            and selected_runtime_id != preferred_runtime_id
        ):
            return {
                "error": (
                    "Preferred Codex runtime mismatch under fail-closed policy; "
                    "pool rebinding is disabled."
                )
            }

    if "env" in pool_result and selection:
        selected_runtime_id = str(pool_result.get("selected_runtime_id") or "").strip()
        resolved_preference_source = preference_source
        if (
            preference_source == "session_lease"
            and preferred_runtime_id
            and selected_runtime_id
            and selected_runtime_id != str(preferred_runtime_id).strip()
        ):
            resolved_preference_source = "lease_rebind"
        pool_result.update(
            {
                "preferred_runtime_id": selection.preferred_runtime_id,
                "binding_runtime_id": preference.get("binding_runtime_id"),
                "binding_state": preference.get("binding_state"),
                "preference_source": resolved_preference_source,
                "policy_mode": selection.policy_mode,
                "requested_workspace_id": selection.requested_workspace_id,
                "effective_workspace_id": selection.effective_workspace_id,
                "auth_workspace_id": selection.auth_workspace_id,
                "source_workspace_id": selection.source_workspace_id,
                "selection_reason": selection.selection_reason,
                "selection_trace": list(selection.trace),
            }
        )
        try:
            binding_service.record_route_resolution(
                selection=selection,
                resolved_runtime_id=selected_runtime_id,
            )
        except Exception:
            logger.warning(
                "Failed to persist Codex route resolution for workspace %s",
                selection.effective_workspace_id,
                exc_info=True,
            )
        if (
            record_runtime_lease
            and normalized_workspace_id
            and normalized_lease_owner_type
            and normalized_lease_owner_id
            and selected_runtime_id
        ):
            try:
                binding_service.record_runtime_lease(
                    workspace_id=normalized_workspace_id,
                    surface=selection.surface,
                    runtime_id=selected_runtime_id,
                    lease_owner_type=normalized_lease_owner_type,
                    lease_owner_id=normalized_lease_owner_id,
                )
            except Exception:
                logger.warning(
                    "Failed to persist Codex runtime lease for workspace %s",
                    normalized_workspace_id,
                    exc_info=True,
                )

    return pool_result


async def resolve_codex_pool_runtime_bundle(
    *,
    workspace_id: str,
    auth_workspace_id: Optional[str] = None,
    source_workspace_id: Optional[str] = None,
    lease_owner_type: Optional[str] = None,
    lease_owner_id: Optional[str] = None,
    excluded_runtime_ids: Optional[set[str]] = None,
    excluded_quota_scope_keys: Optional[set[str]] = None,
    require_probe_available: bool = False,
    fail_closed_session_lease: bool = True,
    record_runtime_lease: bool = False,
) -> dict[str, Any]:
    return await asyncio.to_thread(
        resolve_codex_pool_runtime_bundle_sync,
        workspace_id=workspace_id,
        auth_workspace_id=auth_workspace_id,
        source_workspace_id=source_workspace_id,
        lease_owner_type=lease_owner_type,
        lease_owner_id=lease_owner_id,
        excluded_runtime_ids=excluded_runtime_ids,
        excluded_quota_scope_keys=excluded_quota_scope_keys,
        require_probe_available=require_probe_available,
        fail_closed_session_lease=fail_closed_session_lease,
        record_runtime_lease=record_runtime_lease,
    )


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


def _normalize_fault_kind(fault_kind: str) -> str:
    normalized = str(fault_kind or "").strip().lower()
    if normalized in {"quota", "rate_limit", "429"}:
        return "quota"
    if normalized in {
        "auth",
        "auth_failure",
        "stale_refresh_token",
        "401",
        "403",
        "unauthorized",
    }:
        return "auth"
    return "runtime"


def report_codex_pool_runtime_fault_sync(
    *,
    runtime_id: str,
    fault_kind: str,
    workspace_id: str = "",
    effective_workspace_id: Optional[str] = None,
    error_code: str = "runtime_error",
    error_text: str = "",
) -> dict[str, Any]:
    from backend.app.services.codex_pool_service import CodexPoolService
    from backend.app.services.executor_binding_service import ExecutorBindingService
    from backend.app.services.codex_runtime_failure_classifier import (
        extract_codex_quota_reset_at,
    )

    normalized_runtime_id = str(runtime_id or "").strip()
    if not normalized_runtime_id:
        return {"reported": False, "error": "runtime_id is required"}

    normalized_fault_kind = _normalize_fault_kind(fault_kind)
    normalized_error_code = str(error_code or "").strip() or (
        "429" if normalized_fault_kind == "quota" else "runtime_error"
    )
    if normalized_fault_kind == "quota":
        result = CodexPoolService().report_quota_exhausted(
            normalized_runtime_id,
            reset_at=extract_codex_quota_reset_at(error_text or ""),
        )
        binding_error_code = "429"
    elif normalized_fault_kind == "auth":
        result = CodexPoolService().report_auth_failure(
            normalized_runtime_id,
            error_code=normalized_error_code,
        )
        binding_error_code = normalized_error_code
    else:
        result = CodexPoolService().report_auth_failure(
            normalized_runtime_id,
            error_code=normalized_error_code,
        )
        binding_error_code = normalized_error_code

    if result is None:
        return {
            "reported": False,
            "error": f"Unknown Codex runtime: {normalized_runtime_id}",
        }

    binding_workspace_id = str(effective_workspace_id or workspace_id or "").strip()
    if binding_workspace_id:
        try:
            ExecutorBindingService().record_runtime_fault(
                workspace_id=binding_workspace_id,
                surface="codex_cli",
                runtime_id=normalized_runtime_id,
                error_code=binding_error_code,
            )
        except Exception:
            logger.warning(
                "Failed to persist Codex runtime fault binding for workspace %s",
                binding_workspace_id,
                exc_info=True,
            )

    return {
        "reported": True,
        "fault_kind": normalized_fault_kind,
        "runtime_id": normalized_runtime_id,
        "workspace_id": binding_workspace_id or None,
        "result": result,
    }


async def report_codex_pool_runtime_fault(
    *,
    runtime_id: str,
    fault_kind: str,
    workspace_id: str = "",
    effective_workspace_id: Optional[str] = None,
    error_code: str = "runtime_error",
    error_text: str = "",
) -> dict[str, Any]:
    return await asyncio.to_thread(
        report_codex_pool_runtime_fault_sync,
        runtime_id=runtime_id,
        fault_kind=fault_kind,
        workspace_id=workspace_id,
        effective_workspace_id=effective_workspace_id,
        error_code=error_code,
        error_text=error_text,
    )


def report_codex_pool_runtime_success_sync(*, runtime_id: str) -> dict[str, Any]:
    from backend.app.services.codex_pool_service import CodexPoolService

    normalized_runtime_id = str(runtime_id or "").strip()
    if not normalized_runtime_id:
        return {"reported": False, "error": "runtime_id is required"}
    result = CodexPoolService().report_runtime_success(normalized_runtime_id)
    if result is None:
        return {
            "reported": False,
            "error": f"Unknown Codex runtime: {normalized_runtime_id}",
        }
    return {
        "reported": True,
        "runtime_id": normalized_runtime_id,
        "result": result,
    }


async def report_codex_pool_runtime_success(*, runtime_id: str) -> dict[str, Any]:
    return await asyncio.to_thread(
        report_codex_pool_runtime_success_sync,
        runtime_id=runtime_id,
    )
