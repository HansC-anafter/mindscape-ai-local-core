import logging

logger = logging.getLogger(__name__)


def _get_codex_pool_bundle(
    workspace_id: str | None = None,
    auth_workspace_id: str | None = None,
    source_workspace_id: str | None = None,
    exclude_runtime_ids: str | None = None,
) -> dict:
    try:
        from backend.app.services.codex_pool_runtime_router import (
            resolve_codex_pool_runtime_bundle_sync,
        )

        excluded_runtime_ids = {
            value.strip()
            for value in str(exclude_runtime_ids or "").split(",")
            if value.strip()
        }
        return resolve_codex_pool_runtime_bundle_sync(
            workspace_id=workspace_id or "",
            auth_workspace_id=auth_workspace_id,
            source_workspace_id=source_workspace_id,
            lease_owner_type=None,
            lease_owner_id=None,
            excluded_runtime_ids=excluded_runtime_ids,
            fail_closed_session_lease=True,
            record_runtime_lease=False,
        )
    except Exception:
        logger.exception("Codex pool token lookup failed")
        return {
            "error": "Codex pool token lookup failed",
        }


def _record_runtime_fault_binding(
    *,
    surface: str,
    runtime_id: str,
    workspace_id: str | None = None,
    effective_workspace_id: str | None = None,
    error_code: str | None = None,
) -> str | None:
    target_workspace_id = str(effective_workspace_id or workspace_id or "").strip()
    if not target_workspace_id:
        return None

    try:
        from backend.app.services.executor_binding_service import ExecutorBindingService

        ExecutorBindingService().record_runtime_fault(
            workspace_id=target_workspace_id,
            surface=surface,
            runtime_id=runtime_id,
            error_code=error_code,
        )
        return target_workspace_id
    except Exception:
        logger.warning(
            "Failed to persist runtime fault binding for workspace %s surface=%s runtime=%s",
            target_workspace_id,
            surface,
            runtime_id,
            exc_info=True,
        )
        return None


def _get_gca_token(
    workspace_id: str | None = None,
    auth_workspace_id: str | None = None,
    source_workspace_id: str | None = None,
) -> dict:
    try:
        from backend.app.services.executor_binding_service import ExecutorBindingService
        from backend.app.services.executor_route_resolver import ExecutorRouteResolver
        from backend.app.services.gca_pool_service import GCAPoolService

        selection = None
        binding_service = ExecutorBindingService()
        if workspace_id:
            selection = ExecutorRouteResolver().resolve(
                surface="gemini_cli",
                workspace_id=workspace_id,
                auth_workspace_id=auth_workspace_id,
                source_workspace_id=source_workspace_id,
            )
        preference = (
            binding_service.resolve_pool_preference(selection=selection)
            if selection
            else {
                "preferred_runtime_id": None,
                "allow_runtime_substitution": False,
                "preference_source": "no_bound_runtime",
                "binding_runtime_id": None,
                "binding_state": None,
            }
        )
        preferred_runtime_id = preference.get("preferred_runtime_id")
        allow_runtime_substitution = bool(preference.get("allow_runtime_substitution", False))
        preference_source = str(preference.get("preference_source") or "no_bound_runtime")
        pool_result = GCAPoolService().get_active_token(
            preferred_runtime_id=preferred_runtime_id,
            allow_runtime_substitution=allow_runtime_substitution,
        )
        if "env" in pool_result:
            if selection:
                pool_result.update(
                    {
                        "preferred_runtime_id": selection.preferred_runtime_id,
                        "binding_runtime_id": preference.get("binding_runtime_id"),
                        "binding_state": preference.get("binding_state"),
                        "preference_source": preference_source,
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
                        resolved_runtime_id=pool_result.get("selected_runtime_id"),
                    )
                except Exception:
                    logger.warning(
                        "Failed to persist GCA executor binding for workspace %s",
                        selection.effective_workspace_id,
                        exc_info=True,
                    )
            return pool_result
        if selection:
            return {
                "error": pool_result.get("error", "workspace-scoped GCA selection failed"),
                "preferred_runtime_id": selection.preferred_runtime_id,
                "binding_runtime_id": preference.get("binding_runtime_id"),
                "binding_state": preference.get("binding_state"),
                "preference_source": preference_source,
                "policy_mode": selection.policy_mode,
                "requested_workspace_id": selection.requested_workspace_id,
                "effective_workspace_id": selection.effective_workspace_id,
                "auth_workspace_id": selection.auth_workspace_id,
                "source_workspace_id": selection.source_workspace_id,
                "selection_reason": selection.selection_reason,
                "selection_trace": list(selection.trace),
            }
        return pool_result
    except Exception:
        if workspace_id:
            logger.exception("Workspace-scoped GCA token lookup failed")
            return {
                "error": f"Workspace-scoped GCA token lookup failed for workspace {workspace_id}",
            }
        logger.exception("GCA pool token lookup failed under fail-closed policy")
        return {
            "error": "GCA pool token lookup failed under fail-closed policy",
        }
