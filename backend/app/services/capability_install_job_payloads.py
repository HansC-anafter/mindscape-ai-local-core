"""Pure payload helpers for capability install jobs."""

from __future__ import annotations

from typing import Any, Dict

from backend.app.routes.core.capability_install_core.restart_policy import (
    apply_restart_decision_to_payload,
)


def _status_url(install_id: str) -> str:
    return f"/api/v1/capability-packs/install-jobs/{install_id}"


def _pipeline_result_to_payload(result: Any) -> Dict[str, Any]:
    payload = {
        "success": bool(getattr(result, "success", False)),
        "capability_code": getattr(result, "capability_code", None),
        "version": getattr(result, "version", None),
        "warnings": list(getattr(result, "warnings", []) or []),
        "restart_required": bool(getattr(result, "restart_required", False)),
        "restart_triggered": bool(getattr(result, "restart_triggered", False)),
        "hot_reload": getattr(result, "hot_reload_result", None),
        "webhook": getattr(result, "webhook_result", None),
        "activation": getattr(result, "activation", None),
        "validation": getattr(result, "validation", None),
        "pack_metadata": getattr(result, "pack_metadata", {}) or {},
    }
    return apply_restart_decision_to_payload(
        payload,
        getattr(result, "restart_decision", {}) or {},
    )
