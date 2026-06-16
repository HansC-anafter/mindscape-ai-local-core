from __future__ import annotations

import concurrent.futures
import os
from typing import Any, Callable, Dict


def build_preview_runtime_audit_payload(
    sync_preview_runtime_audit_fn: Callable[[], Dict[str, Any]],
) -> Dict[str, Any]:
    timeout_seconds = float(
        os.getenv("COMFYUI_RUNTIME_HEALTH_AUDIT_TIMEOUT_SECONDS", "5")
    )
    executor = concurrent.futures.ThreadPoolExecutor(max_workers=1)
    try:
        future = executor.submit(sync_preview_runtime_audit_fn)
        sync_payload = future.result(timeout=max(timeout_seconds, 1.0))
    except concurrent.futures.TimeoutError:
        return {
            "status": "failed",
            "stderr": "preview_runtime_audit_timeout",
            "returncode": 124,
            "command": [],
            "summary_text": "",
            "audit_verdict": "audit_timeout",
            "effective_runtime_config": {},
            "dependency_conflicts": [],
            "python_env": {},
            "process_profiles": [],
            "shared_venv_risk": {"state": "unknown"},
            "kimodo_preflight": {"state": "unknown", "blocked_reasons": []},
            "kimodo_isolated_runtime": {"runtime_state": "unknown"},
            "recommended_transformers_strategy": "audit_timeout",
        }
    except Exception as exc:
        return {
            "status": "failed",
            "stderr": str(exc),
            "returncode": 1,
            "command": [],
            "summary_text": "",
            "audit_verdict": "audit_unavailable",
            "effective_runtime_config": {},
            "dependency_conflicts": [],
            "python_env": {},
            "process_profiles": [],
            "shared_venv_risk": {"state": "unknown"},
            "kimodo_preflight": {"state": "unknown", "blocked_reasons": []},
            "kimodo_isolated_runtime": {"runtime_state": "unknown"},
            "recommended_transformers_strategy": "audit_unavailable",
        }
    finally:
        executor.shutdown(wait=False, cancel_futures=True)

    readiness = dict(sync_payload.get("readiness") or {})
    return {
        "status": str(sync_payload.get("status") or ""),
        "stderr": str(sync_payload.get("stderr") or ""),
        "returncode": int(sync_payload.get("returncode", 0) or 0),
        "command": list(sync_payload.get("command") or []),
        "summary_text": str(
            readiness.get("summary_text") or sync_payload.get("stdout") or ""
        ),
        "audit_verdict": str(readiness.get("audit_verdict") or "audit_unavailable"),
        "effective_runtime_config": dict(
            readiness.get("effective_runtime_config") or {}
        ),
        "dependency_conflicts": list(readiness.get("dependency_conflicts") or []),
        "python_env": dict(readiness.get("python_env") or {}),
        "process_profiles": list(readiness.get("process_profiles") or []),
        "shared_venv_risk": dict(readiness.get("shared_venv_risk") or {}),
        "kimodo_preflight": dict(readiness.get("kimodo_preflight") or {}),
        "kimodo_isolated_runtime": dict(
            readiness.get("kimodo_isolated_runtime") or {}
        ),
        "recommended_transformers_strategy": str(
            readiness.get("recommended_transformers_strategy") or "audit_unavailable"
        ),
    }
