from __future__ import annotations

from typing import Any, Callable, Dict


def merge_regional_adapter_host_readiness(
    *,
    plan: Dict[str, Any],
    sync_regional_adapter_runtime_fn: Callable[[], Dict[str, Any]],
) -> Dict[str, Any]:
    merged_plan = dict(plan)
    try:
        sync_payload = sync_regional_adapter_runtime_fn()
    except Exception as exc:
        merged_plan["host_runtime_readiness"] = {
            "status": "unavailable",
            "stderr": str(exc),
            "returncode": 1,
            "readiness": {},
        }
        return merged_plan

    readiness = dict(sync_payload.get("readiness") or {})
    merged_plan["host_runtime_readiness"] = {
        "status": str(sync_payload.get("status") or ""),
        "stderr": str(sync_payload.get("stderr") or ""),
        "returncode": int(sync_payload.get("returncode", 0) or 0),
        "readiness": readiness,
    }
    if not readiness:
        return merged_plan

    required_file_results = dict(readiness.get("required_file_results") or {})
    host_missing_model_files: list[str] = []
    host_invalid_model_files: list[str] = []
    host_model_file_health: Dict[str, Dict[str, Any]] = {}
    for result in required_file_results.values():
        model_name = str(result.get("path") or "").strip()
        if not model_name:
            continue
        exists = bool(result.get("exists"))
        valid = bool(result.get("valid", True))
        resolved_path = str(result.get("resolved_path") or "")
        host_model_file_health[model_name] = {
            "path": resolved_path,
            "exists": exists,
            "valid": valid,
        }
        if not exists:
            if model_name not in host_missing_model_files:
                host_missing_model_files.append(model_name)
        elif not valid:
            if model_name not in host_invalid_model_files:
                host_invalid_model_files.append(model_name)
            if model_name not in host_missing_model_files:
                host_missing_model_files.append(model_name)

    merged_plan["model_file_health"] = {
        **dict(merged_plan.get("model_file_health") or {}),
        **host_model_file_health,
    }
    merged_plan["missing_model_files"] = list(
        dict.fromkeys(
            list(merged_plan.get("missing_model_files") or [])
            + host_missing_model_files
        )
    )
    merged_plan["invalid_model_files"] = list(
        dict.fromkeys(
            list(merged_plan.get("invalid_model_files") or [])
            + host_invalid_model_files
        )
    )
    merged_plan["model_bootstrap_required"] = bool(
        merged_plan.get("missing_model_files")
    )

    if readiness.get("ready", True):
        return merged_plan

    if not merged_plan.get("missing_model_files") and not merged_plan.get(
        "invalid_model_files"
    ):
        return merged_plan

    required_specs = list(merged_plan.get("required_runtime_install_specs") or [])
    install_blockers = list(merged_plan.get("install_blockers") or [])
    selected_backend_family = str(merged_plan.get("selected_backend_family") or "")
    supports_auto_install = bool(merged_plan.get("supports_auto_install"))
    if selected_backend_family == "manual_existing_nodes":
        merged_plan["manual_only_specs"] = required_specs
        merged_plan["source_install_specs"] = []
        merged_plan["readiness_state"] = "manual_only_required"
        merged_plan["narrative_state"] = "manual_only_required"
        merged_plan["install_action_state"] = "manual_only"
    else:
        merged_plan["missing_runtime_install_specs"] = required_specs
        merged_plan["source_install_specs"] = required_specs
        merged_plan["manual_only_specs"] = []
        merged_plan["readiness_state"] = "source_install_required"
        merged_plan["narrative_state"] = "source_install_required"
        merged_plan["source_install_actionable"] = bool(required_specs) and not install_blockers
        merged_plan["install_action_state"] = (
            "actionable_source_install"
            if merged_plan["source_install_actionable"]
            else "blocked_configuration"
        )
        if not supports_auto_install and "preset_manual_only" not in install_blockers:
            install_blockers.append("preset_manual_only")
            merged_plan["install_blockers"] = install_blockers

    host_summary = str(readiness.get("summary_text") or "").strip()
    configuration_hints = list(merged_plan.get("configuration_hints") or [])
    if host_summary:
        configuration_hints.append(
            "Host readiness check reports regional runtime is not ready:\n"
            + host_summary
        )
    merged_plan["configuration_hints"] = configuration_hints
    return merged_plan
