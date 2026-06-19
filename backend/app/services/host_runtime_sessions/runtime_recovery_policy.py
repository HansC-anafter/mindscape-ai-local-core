"""Recovery policy helpers for direct host runtime sessions."""

from __future__ import annotations

from typing import Any, Mapping

from backend.app.services.codex_runtime_failure_classifier import (
    classify_codex_cli_runtime_failure,
)


DIRECT_CODEX_RUNTIME_ID = "host_runtime_direct_codex_cli"
DIRECT_CODEX_RUNTIME_MODE = "direct_subprocess"
DIRECT_CODEX_RECOVERY_POLICY = "direct_codex_cli"


def build_direct_codex_auth_bundle(workspace_id: str) -> dict[str, Any]:
    """Build the direct Codex CLI runtime contract for host-side sessions."""

    return {
        "env": {},
        "selected_runtime_id": DIRECT_CODEX_RUNTIME_ID,
        "effective_workspace_id": str(workspace_id or ""),
        "runtime_mode": DIRECT_CODEX_RUNTIME_MODE,
        "pool_managed": False,
        "recovery_policy": DIRECT_CODEX_RECOVERY_POLICY,
    }


def build_direct_codex_excluded_bundle(workspace_id: str) -> dict[str, Any]:
    """Build a terminal direct-runtime bundle when the only local runtime was excluded."""

    return {
        "env": {},
        "selected_runtime_id": "",
        "effective_workspace_id": str(workspace_id or ""),
        "runtime_mode": DIRECT_CODEX_RUNTIME_MODE,
        "pool_managed": False,
        "recovery_policy": DIRECT_CODEX_RECOVERY_POLICY,
        "error": "direct_codex_runtime_excluded",
    }


def is_direct_codex_auth_bundle(bundle: Mapping[str, Any] | None) -> bool:
    """Return whether an auth bundle represents the host direct Codex CLI path."""

    if not isinstance(bundle, Mapping):
        return False
    return (
        bundle.get("runtime_mode") == DIRECT_CODEX_RUNTIME_MODE
        and bundle.get("pool_managed") is False
        and bundle.get("recovery_policy") == DIRECT_CODEX_RECOVERY_POLICY
    )


def classify_direct_codex_failure(message: str) -> dict[str, str]:
    """Classify direct Codex CLI failures into user-actionable metadata."""

    classification = classify_codex_cli_runtime_failure(message)
    fault_kind = str(classification.get("fault_kind") or "runtime")
    error_code = str(classification.get("error_code") or "runtime_error")

    if error_code == "codex_cli_panic":
        return {
            "failure_kind": "codex_cli_panic",
            "error_code": error_code,
            "recovery_action": "repair_or_update_local_codex_cli",
        }
    if error_code == "codex_cli_config_invalid":
        return {
            "failure_kind": "codex_cli_config_invalid",
            "error_code": error_code,
            "recovery_action": "fix_local_codex_cli_config",
        }
    if error_code == "timeout":
        return {
            "failure_kind": "codex_cli_stall_no_activity",
            "error_code": error_code,
            "recovery_action": "restart_bridge_after_confirming_codex_cli_smoke",
        }
    if error_code == "runtime_not_found":
        return {
            "failure_kind": "codex_cli_not_found",
            "error_code": error_code,
            "recovery_action": "install_or_select_codex_cli_binary",
        }
    if fault_kind == "auth":
        return {
            "failure_kind": "codex_cli_auth_failure",
            "error_code": error_code,
            "recovery_action": "refresh_local_codex_cli_login",
        }
    if fault_kind == "quota":
        return {
            "failure_kind": "codex_cli_quota_exhausted",
            "error_code": error_code,
            "recovery_action": "wait_for_codex_quota_or_switch_runtime",
        }
    return {
        "failure_kind": "codex_cli_runtime_error",
        "error_code": error_code,
        "recovery_action": "inspect_local_codex_cli_stderr",
    }


def build_direct_codex_failure_metadata(
    *,
    selected_runtime_id: str | None,
    workspace_id: str,
    effective_workspace_id: str,
    error_text: str,
    stage: str,
    exit_code: int | None = None,
    stdout_tail: str = "",
    stderr_tail: str = "",
) -> dict[str, Any]:
    """Build terminal metadata for direct Codex CLI failures."""

    classified = classify_direct_codex_failure(error_text)
    metadata: dict[str, Any] = {
        "runtime_mode": DIRECT_CODEX_RUNTIME_MODE,
        "pool_managed": False,
        "recovery_policy": DIRECT_CODEX_RECOVERY_POLICY,
        "selected_runtime_id": selected_runtime_id or DIRECT_CODEX_RUNTIME_ID,
        "workspace_id": workspace_id or None,
        "effective_workspace_id": effective_workspace_id or workspace_id or None,
        "failure_stage": stage,
        **classified,
    }
    if exit_code is not None:
        metadata["exit_code"] = exit_code
    if stdout_tail:
        metadata["stdout_tail"] = stdout_tail
    if stderr_tail:
        metadata["stderr_tail"] = stderr_tail
    return metadata
