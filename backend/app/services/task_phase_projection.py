"""Helpers for deriving user-facing task phases from coarse task status."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Dict, Optional


_WATCHDOG_STATE_DIR = Path(
    os.getenv("MULTIMODAL_WATCHDOG_STATE_DIR", "/app/logs/mlx-watchdog")
)
_WATCHDOG_STATE_FILE = _WATCHDOG_STATE_DIR / "inflight_request.json"


def _as_dict(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _normalize_status(value: Any) -> str:
    if hasattr(value, "value"):
        value = value.value
    return str(value or "").strip().lower()


def load_mlx_watchdog_state() -> Dict[str, Any]:
    """Return the current MLX inflight request sentinel if present."""
    try:
        if not _WATCHDOG_STATE_FILE.exists():
            return {}
        payload = json.loads(_WATCHDOG_STATE_FILE.read_text(encoding="utf-8"))
        return payload if isinstance(payload, dict) else {}
    except Exception:
        return {}


def derive_task_status_phase(
    task_payload: Dict[str, Any],
    *,
    watchdog_state: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Project a coarse task status into a more precise user-facing phase."""
    payload = _as_dict(task_payload)
    status = _normalize_status(payload.get("status"))
    ctx = _as_dict(payload.get("execution_context"))
    inputs = _as_dict(ctx.get("inputs"))
    pack_id = str(payload.get("pack_id") or ctx.get("playbook_code") or "").strip()

    if status in {"pending", "queued", "paused"}:
        return {
            "status_phase": "queued",
            "status_phase_group": "queued",
        }

    if status in {"succeeded", "completed"}:
        return {
            "status_phase": "completed",
            "status_phase_group": "terminal",
        }

    if status in {"failed", "cancelled", "cancelled_by_user", "expired"}:
        return {
            "status_phase": "failed",
            "status_phase_group": "terminal",
        }

    if status != "running":
        return {
            "status_phase": status or "unknown",
            "status_phase_group": "unknown",
        }

    if pack_id != "ig_analyze_pinned_reference":
        return {
            "status_phase": "running",
            "status_phase_group": "running",
        }

    current_watchdog = (
        watchdog_state if isinstance(watchdog_state, dict) else load_mlx_watchdog_state()
    )
    watchdog_status = _normalize_status(current_watchdog.get("status"))
    watchdog_reference_id = str(current_watchdog.get("reference_id") or "").strip()
    watchdog_phase = _normalize_status(current_watchdog.get("progress_phase"))
    reference_id = str(inputs.get("reference_id") or "").strip()

    if watchdog_status == "active" and reference_id and watchdog_reference_id == reference_id:
        status_phase = "mlx_active"
        if watchdog_phase in {"accepted", "embedding", "prefill"}:
            status_phase = "mlx_prefill"
        elif watchdog_phase in {"decode_ready", "generating"}:
            status_phase = "mlx_generating"
        return {
            "status_phase": status_phase,
            "status_phase_group": "running",
            "status_phase_request_id": current_watchdog.get("request_id"),
            "status_phase_model_id": current_watchdog.get("model_id"),
        }

    if watchdog_status == "active":
        return {
            "status_phase": "waiting_mlx",
            "status_phase_group": "running",
        }

    return {
        "status_phase": "preparing",
        "status_phase_group": "running",
    }


def enrich_task_payload_with_phase(
    task_payload: Dict[str, Any],
    *,
    watchdog_state: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    projected = dict(task_payload)
    projected.update(
        derive_task_status_phase(projected, watchdog_state=watchdog_state)
    )
    return projected
