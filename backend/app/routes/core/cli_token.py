"""
CLI token endpoint.

Returns auth environment variables for CLI bridge processes.
"""

import logging
import os
from typing import Any

from fastapi import APIRouter, HTTPException, Query

from backend.app.routes.core.cli_token_core.agent_context import (
    _get_pack_agent_guides,
    get_agent_context_payload,
)
from backend.app.routes.core.cli_token_core.host_session_runtime import (
    _can_shadow_host_session_candidate,
    _clear_stale_shadow_marker,
    _coerce_json_dict,
    _default_pool_group_for_surface,
    _effective_host_session_pool_enabled,
    _load_workspace_owner_user_id,
    _prepare_host_session_runtime_metadata,
    _register_host_session_runtime,
    _stable_host_session_runtime_id,
    _upsert_host_session_runtime,
    _upsert_host_session_runtime_sql,
)
from backend.app.routes.core.cli_token_core.schemas import (
    RegisterHostSessionRuntimeRequest,
)
from backend.app.routes.core.cli_token_core.token_bundles import (
    _get_codex_pool_bundle,
    _get_gca_token,
    _record_runtime_fault_binding,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])


@router.get("/cli-token")
async def get_cli_token(
    workspace_id: str | None = Query(None),
    auth_workspace_id: str | None = Query(None),
    source_workspace_id: str | None = Query(None),
    surface: str | None = Query(None),
    exclude_runtime_ids: str | None = Query(None),
):
    try:
        from backend.app.services.system_settings_store import SystemSettingsStore

        settings = SystemSettingsStore()
        surface_name = (surface or "gemini_cli").strip().lower()

        if surface_name == "codex_cli":
            pool_result = _get_codex_pool_bundle(
                workspace_id=workspace_id,
                auth_workspace_id=auth_workspace_id,
                source_workspace_id=source_workspace_id,
                exclude_runtime_ids=exclude_runtime_ids,
            )
            if "env" in pool_result:
                return {
                    "auth_mode": pool_result.get("auth_mode", "host_session"),
                    "env": pool_result.get("env", {}),
                    "selected_runtime_id": pool_result.get("selected_runtime_id"),
                    "preferred_runtime_id": pool_result.get("preferred_runtime_id"),
                    "policy_mode": pool_result.get("policy_mode"),
                    "available_runtime_count": pool_result.get(
                        "available_runtime_count"
                    ),
                    "available_quota_scope_count": pool_result.get(
                        "available_quota_scope_count"
                    ),
                    "requested_workspace_id": pool_result.get("requested_workspace_id"),
                    "effective_workspace_id": pool_result.get("effective_workspace_id"),
                    "auth_workspace_id": pool_result.get("auth_workspace_id"),
                    "source_workspace_id": pool_result.get("source_workspace_id"),
                    "selection_reason": pool_result.get("selection_reason"),
                    "selection_trace": pool_result.get("selection_trace", []),
                }

            return {
                "auth_mode": "codex_cli",
                "env": {},
                "error": pool_result.get(
                    "error",
                    "Codex CLI runtime is not available through executor route policy.",
                ),
                "preferred_runtime_id": pool_result.get("preferred_runtime_id"),
                "policy_mode": pool_result.get("policy_mode"),
                "requested_workspace_id": pool_result.get("requested_workspace_id"),
                "effective_workspace_id": pool_result.get("effective_workspace_id"),
                "auth_workspace_id": pool_result.get("auth_workspace_id"),
                "source_workspace_id": pool_result.get("source_workspace_id"),
                "selection_reason": pool_result.get("selection_reason"),
                "selection_trace": pool_result.get("selection_trace", []),
            }

        if surface_name == "claude_code_cli":
            api_key = settings.get("claude_api_key", "")
            if not api_key:
                api_key = os.environ.get("ANTHROPIC_API_KEY", "")
            if api_key:
                return {
                    "auth_mode": "anthropic_api_key",
                    "env": {"ANTHROPIC_API_KEY": api_key},
                }
            return {
                "auth_mode": "host_session",
                "env": {},
                "note": "Claude Code CLI will use any credentials already stored on the host.",
            }

        auth_mode = settings.get("gemini_cli_auth_mode", "gca")
        agent_model = settings.get("agent_cli_model", "gemini-2.5-pro")

        if auth_mode == "gca":
            result = _get_gca_token(
                workspace_id=workspace_id,
                auth_workspace_id=auth_workspace_id,
                source_workspace_id=source_workspace_id,
            )
            if "error" in result:
                logger.warning("GCA token retrieval failed: %s", result["error"])
                return {
                    "auth_mode": "gca",
                    "env": {},
                    "error": result["error"],
                    "model": agent_model,
                    "preferred_runtime_id": result.get("preferred_runtime_id"),
                    "policy_mode": result.get("policy_mode"),
                    "requested_workspace_id": result.get("requested_workspace_id"),
                    "effective_workspace_id": result.get("effective_workspace_id"),
                    "auth_workspace_id": result.get("auth_workspace_id"),
                    "source_workspace_id": result.get("source_workspace_id"),
                    "selection_reason": result.get("selection_reason"),
                    "selection_trace": result.get("selection_trace", []),
                }
            return {
                "auth_mode": "gca",
                "env": result["env"],
                "model": agent_model,
                "selected_runtime_id": result.get("selected_runtime_id"),
                "preferred_runtime_id": result.get("preferred_runtime_id"),
                "policy_mode": result.get("policy_mode"),
                "requested_workspace_id": result.get("requested_workspace_id"),
                "effective_workspace_id": result.get("effective_workspace_id"),
                "auth_workspace_id": result.get("auth_workspace_id"),
                "source_workspace_id": result.get("source_workspace_id"),
                "selection_reason": result.get("selection_reason"),
                "selection_trace": result.get("selection_trace", []),
            }

        if auth_mode == "gemini_api_key":
            api_key = settings.get("gemini_api_key", "")
            if not api_key:
                api_key = os.environ.get("GEMINI_API_KEY", "")
            if not api_key:
                return {
                    "auth_mode": auth_mode,
                    "env": {},
                    "error": "gemini_api_key not configured in system_settings",
                }
            return {
                "auth_mode": auth_mode,
                "env": {"GEMINI_API_KEY": api_key},
                "model": agent_model,
            }

        if auth_mode == "vertex_ai":
            project = settings.get(
                "google_cloud_project",
                os.environ.get("GOOGLE_CLOUD_PROJECT", ""),
            )
            location = settings.get(
                "google_cloud_location",
                os.environ.get("GOOGLE_CLOUD_LOCATION", "us-central1"),
            )
            if not project:
                return {
                    "auth_mode": auth_mode,
                    "env": {},
                    "error": "google_cloud_project not configured",
                }
            return {
                "auth_mode": auth_mode,
                "env": {
                    "GOOGLE_GENAI_USE_VERTEXAI": "true",
                    "GOOGLE_CLOUD_PROJECT": project,
                    "GOOGLE_CLOUD_LOCATION": location,
                },
                "model": agent_model,
            }

        return {
            "auth_mode": auth_mode,
            "env": {},
            "error": f"Unknown auth_mode: {auth_mode}",
            "model": agent_model,
        }

    except Exception as exc:
        logger.error("Failed to retrieve CLI auth config: %s", exc)
        surface_name = (surface or "gemini_cli").strip().lower()
        if surface_name == "codex_cli":
            api_key = os.environ.get("OPENAI_API_KEY", "")
            return {
                "auth_mode": "openai_api_key" if api_key else "host_session",
                "env": {"OPENAI_API_KEY": api_key} if api_key else {},
                "warning": f"system_settings unavailable ({exc}), using host fallback",
            }
        if surface_name == "claude_code_cli":
            api_key = os.environ.get("ANTHROPIC_API_KEY", "")
            return {
                "auth_mode": "anthropic_api_key" if api_key else "host_session",
                "env": {"ANTHROPIC_API_KEY": api_key} if api_key else {},
                "warning": f"system_settings unavailable ({exc}), using host fallback",
            }
        api_key = os.environ.get("GEMINI_API_KEY", "")
        if api_key:
            return {
                "auth_mode": "gemini_api_key",
                "env": {"GEMINI_API_KEY": api_key},
                "warning": f"system_settings unavailable ({exc}), using env fallback",
            }
        return {
            "auth_mode": "unknown",
            "env": {},
            "error": f"system_settings unavailable and no env fallback: {exc}",
        }


@router.post("/cli-runtime/register-host-session")
async def register_host_session_runtime(
    request: RegisterHostSessionRuntimeRequest,
) -> dict[str, Any]:
    surface_name = (request.surface or "").strip().lower()
    if surface_name != "codex_cli":
        raise HTTPException(
            status_code=400,
            detail=f"Host-session runtime registration is not implemented for {surface_name}",
        )

    owner_user_id = str(request.owner_user_id or "").strip()
    if not owner_user_id:
        owner_user_id = _load_workspace_owner_user_id(request.workspace_id) or ""
    if not owner_user_id:
        raise HTTPException(
            status_code=404,
            detail=f"Workspace not found or owner unavailable: {request.workspace_id}",
        )

    runtime = _register_host_session_runtime(
        owner_user_id=owner_user_id,
        request=request,
    )
    return {
        "registered": True,
        "runtime_id": runtime.get("runtime_id") or runtime.get("id"),
        "owner_user_id": owner_user_id,
        "runtime": runtime,
    }


@router.post("/runtime-quota-exhausted")
async def report_runtime_quota_exhausted(
    runtime_id: str = Query(...),
    surface: str = Query(...),
    workspace_id: str | None = Query(None),
    effective_workspace_id: str | None = Query(None),
    error_text: str | None = Query(None),
):
    surface_name = (surface or "").strip().lower()
    if not runtime_id.strip():
        return {"reported": False, "error": "runtime_id is required"}

    if surface_name == "codex_cli":
        from backend.app.services.codex_pool_runtime_router import (
            report_codex_pool_runtime_fault_sync,
        )

        report = report_codex_pool_runtime_fault_sync(
            runtime_id=runtime_id.strip(),
            workspace_id=workspace_id,
            effective_workspace_id=effective_workspace_id,
            fault_kind="quota",
            error_code="429",
            error_text=error_text or "",
        )
        if not report.get("reported"):
            return report
        result = report.get("result") or {}
        return {
            "reported": True,
            "surface": surface_name,
            "runtime_id": runtime_id.strip(),
            "cooldown_until": result.get("cooldown_until"),
            "binding_workspace_id": report.get("workspace_id"),
        }

    if surface_name == "gemini_cli":
        from backend.app.services.gca_pool_service import GCAPoolService

        result = GCAPoolService().report_quota_exhausted(runtime_id.strip())
        if result is None:
            return {"reported": False, "error": f"Unknown GCA runtime: {runtime_id}"}
        binding_workspace_id = _record_runtime_fault_binding(
            surface=surface_name,
            runtime_id=runtime_id.strip(),
            workspace_id=workspace_id,
            effective_workspace_id=effective_workspace_id,
            error_code="429",
        )
        return {
            "reported": True,
            "surface": surface_name,
            "runtime_id": runtime_id.strip(),
            "cooldown_until": result.get("cooldown_until"),
            "binding_workspace_id": binding_workspace_id,
        }

    return {
        "reported": False,
        "error": f"Quota reporting is not implemented for surface '{surface_name}'",
    }


@router.post("/runtime-auth-failure")
async def report_runtime_auth_failure(
    runtime_id: str = Query(...),
    surface: str = Query(...),
    error_code: str = Query("401"),
    workspace_id: str | None = Query(None),
    effective_workspace_id: str | None = Query(None),
):
    surface_name = (surface or "").strip().lower()
    if not runtime_id.strip():
        return {"reported": False, "error": "runtime_id is required"}

    if surface_name == "codex_cli":
        from backend.app.services.codex_pool_runtime_router import (
            report_codex_pool_runtime_fault_sync,
        )

        report = report_codex_pool_runtime_fault_sync(
            runtime_id=runtime_id.strip(),
            workspace_id=workspace_id,
            effective_workspace_id=effective_workspace_id,
            fault_kind="auth",
            error_code=error_code.strip() or "401",
        )
        if not report.get("reported"):
            return report
        result = report.get("result") or {}
        return {
            "reported": True,
            "surface": surface_name,
            "runtime_id": runtime_id.strip(),
            "cooldown_until": result.get("cooldown_until"),
            "error_code": result.get("last_error_code"),
            "binding_workspace_id": report.get("workspace_id"),
        }

    return {
        "reported": False,
        "error": f"Auth failure reporting is not implemented for surface '{surface_name}'",
    }


@router.post("/runtime-success")
async def report_runtime_success(
    runtime_id: str = Query(...),
    surface: str = Query(...),
):
    surface_name = (surface or "").strip().lower()
    if not runtime_id.strip():
        return {"reported": False, "error": "runtime_id is required"}

    if surface_name == "codex_cli":
        from backend.app.services.codex_pool_runtime_router import (
            report_codex_pool_runtime_success_sync,
        )

        report = report_codex_pool_runtime_success_sync(runtime_id=runtime_id.strip())
        if not report.get("reported"):
            return report
        result = report.get("result") or {}
        return {
            "reported": True,
            "surface": surface_name,
            "runtime_id": runtime_id.strip(),
            "cooldown_until": result.get("cooldown_until"),
        }

    return {
        "reported": False,
        "error": f"Success reporting is not implemented for surface '{surface_name}'",
    }


@router.post("/runtime-requalify")
async def requalify_runtime_pool(
    surface: str = Query(...),
    runtime_id: str | None = Query(None),
    reason: str = Query("manual_override"),
    limit: int | None = Query(None),
):
    surface_name = (surface or "").strip().lower()
    if surface_name != "codex_cli":
        return {
            "requalified": False,
            "error": f"Runtime requalification is not implemented for surface '{surface_name}'",
        }

    from backend.app.services.codex_pool_requalification_service import (
        CodexPoolRequalificationService,
    )

    service = CodexPoolRequalificationService()
    normalized_runtime_id = str(runtime_id or "").strip()
    if normalized_runtime_id:
        result = service.requalify_runtime(
            normalized_runtime_id,
            reason=str(reason or "").strip() or "manual_override",
        )
        if result is None:
            return {
                "requalified": False,
                "error": f"Unknown Codex runtime: {normalized_runtime_id}",
            }
        return {
            "requalified": True,
            "surface": surface_name,
            "runtime_id": normalized_runtime_id,
            "result": result,
        }

    summary = service.sweep_due_runtimes(limit=limit)
    return {
        "requalified": True,
        "surface": surface_name,
        "mode": "sweep_due",
        "summary": summary.to_payload(),
    }


@router.get("/agent-context")
async def get_agent_context():
    return get_agent_context_payload()
