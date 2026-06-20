"""Payload helpers for runtime workflow execution."""

import uuid
from typing import Any, Dict, Optional


def _resolve_execution_id(normalized_inputs: Optional[Dict[str, Any]]) -> str:
    if isinstance(normalized_inputs, dict):
        existing = normalized_inputs.get("execution_id")
        if isinstance(existing, str) and existing.strip():
            return existing.strip()
    return str(uuid.uuid4())


def _extract_execution_backend_hint(
    normalized_inputs: Optional[Dict[str, Any]],
) -> Optional[str]:
    if not isinstance(normalized_inputs, dict):
        return None
    backend_hint = normalized_inputs.get("execution_backend")
    if isinstance(backend_hint, str) and backend_hint:
        return backend_hint
    return None


def _merge_task_params(
    existing_params: Any,
    normalized_inputs: Optional[Dict[str, Any]],
) -> Dict[str, Any]:
    merged: Dict[str, Any] = {}
    if isinstance(normalized_inputs, dict):
        merged.update(normalized_inputs)
    if isinstance(existing_params, dict):
        merged.update(existing_params)
    return merged


def _build_runtime_task_context(
    *,
    playbook_code: str,
    execution_id: str,
    normalized_inputs: Dict[str, Any],
    workspace_id: Optional[str],
    project_id: Optional[str],
    profile_id: str,
    execution_backend_hint: Optional[str],
) -> Dict[str, Any]:
    context = {
        "playbook_code": playbook_code,
        "execution_id": execution_id,
        "status": "running",
        "inputs": normalized_inputs,
        "workspace_id": workspace_id,
        "project_id": project_id,
        "profile_id": profile_id,
        "meeting_session_id": normalized_inputs.get("meeting_session_id"),
        "thread_id": normalized_inputs.get("thread_id"),
    }
    if execution_backend_hint:
        context["execution_backend_hint"] = execution_backend_hint
    return context


def _extract_step_and_output_payloads(
    runtime_result: Any,
) -> tuple[Dict[str, Any], Dict[str, Any]]:
    step_outputs_payload: Dict[str, Any] = {}
    outputs_payload: Dict[str, Any] = {}
    metadata = getattr(runtime_result, "metadata", None) or {}
    steps_meta = metadata.get("steps") if isinstance(metadata, dict) else None

    if isinstance(steps_meta, dict):
        for step_result in steps_meta.values():
            if not isinstance(step_result, dict):
                continue
            if isinstance(step_result.get("step_outputs"), dict) and step_result["step_outputs"]:
                step_outputs_payload = step_result["step_outputs"]
            if isinstance(step_result.get("outputs"), dict) and step_result["outputs"]:
                outputs_payload = step_result["outputs"]
            if step_outputs_payload or outputs_payload:
                break

    outputs = getattr(runtime_result, "outputs", None)
    if not step_outputs_payload and isinstance(outputs, dict):
        step_outputs_payload = outputs
    if not outputs_payload and isinstance(outputs, dict):
        outputs_payload = outputs
    return step_outputs_payload, outputs_payload


def _build_canonical_workflow_result(
    *,
    result: Optional[Dict[str, Any]],
    runtime_result: Any,
    workflow_failed: bool,
    step_outputs_payload: Dict[str, Any],
    outputs_payload: Dict[str, Any],
) -> Dict[str, Any]:
    canonical_result = dict(result) if isinstance(result, dict) else {}
    if not canonical_result.get("status"):
        canonical_result["status"] = (
            "failed"
            if workflow_failed
            else getattr(runtime_result, "status", None) or "failed"
        )

    if step_outputs_payload:
        existing_step_outputs = canonical_result.get("step_outputs")
        if isinstance(existing_step_outputs, dict):
            merged_step_outputs = dict(step_outputs_payload)
            merged_step_outputs.update(existing_step_outputs)
            canonical_result["step_outputs"] = merged_step_outputs
        else:
            canonical_result["step_outputs"] = step_outputs_payload

    if outputs_payload:
        existing_outputs = canonical_result.get("outputs")
        if isinstance(existing_outputs, dict):
            merged_outputs = dict(outputs_payload)
            merged_outputs.update(existing_outputs)
            canonical_result["outputs"] = merged_outputs
        else:
            canonical_result["outputs"] = outputs_payload

    return canonical_result


def _extract_sandbox_id(runtime_result: Any) -> Optional[str]:
    metadata = getattr(runtime_result, "metadata", None) or {}
    if isinstance(metadata, dict):
        sandbox_id = metadata.get("sandbox_id")
        if isinstance(sandbox_id, str) and sandbox_id:
            return sandbox_id
        steps = metadata.get("steps")
        if isinstance(steps, dict):
            for step_result in steps.values():
                if isinstance(step_result, dict):
                    sandbox_id = step_result.get("sandbox_id")
                    if isinstance(sandbox_id, str) and sandbox_id:
                        return sandbox_id
    return None
