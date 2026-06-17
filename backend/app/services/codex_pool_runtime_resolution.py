"""Codex pool runtime bundle resolution."""

from __future__ import annotations

import asyncio
import logging
from typing import Any, Optional

logger = logging.getLogger("backend.app.services.codex_pool_runtime_router")


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
