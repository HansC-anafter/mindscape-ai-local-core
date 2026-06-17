"""Codex pool runtime fault and success reporting."""

from __future__ import annotations

import asyncio
import logging
from typing import Any, Optional

logger = logging.getLogger("backend.app.services.codex_pool_runtime_router")


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
