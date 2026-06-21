"""Pure result sidecar construction for the pack dispatch adapter."""

import hashlib
import json
from typing import Any, Dict, List, Optional

PARSER_ID = "pack_dispatch_adapter_v1"
PROVENANCE_SCHEMA_VERSION = "1.1"


def build_result_sidecar(
    *,
    result_data: Any,
    playbook_code: Optional[str] = None,
    playbook_spec: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Build a provenance sidecar without mutating raw playbook output."""
    sidecar: Dict[str, Any] = {
        "provenance_schema_version": PROVENANCE_SCHEMA_VERSION,
        "playbook_code": playbook_code,
        "parsed_by": PARSER_ID,
        "trace_index": {"entries": []},
    }

    if not isinstance(result_data, dict):
        sidecar["output_hash"] = compute_hash(result_data)
        return sidecar

    sidecar["output_hash"] = compute_hash(result_data)
    context_attachments = extract_context_attachments(result_data)
    if context_attachments:
        sidecar["context_attachments"] = context_attachments

    inspection_roots = candidate_result_roots(
        result_data=result_data,
        playbook_code=playbook_code,
    )

    if playbook_spec:
        spec_outputs = playbook_spec.get("outputs", {})
        if isinstance(spec_outputs, dict):
            matched: Dict[str, Dict[str, Any]] = {}
            resolved_outputs: Dict[str, Any] = {}
            for output_name, output_def in spec_outputs.items():
                if not isinstance(output_def, dict):
                    output_def = {}
                source = output_def.get("source", "")
                value = resolve_output_value(
                    roots=inspection_roots,
                    output_name=output_name,
                    source=source,
                )
                if value is not None:
                    matched[output_name] = {
                        "type": output_def.get("type", "unknown"),
                        "source": source,
                        "resolved": True,
                        "value_present": has_material_value(value),
                    }
                    summarized = summarize_output_value(output_name, value)
                    if summarized is not None:
                        resolved_outputs[output_name] = summarized
                else:
                    matched[output_name] = {
                        "type": output_def.get("type", "unknown"),
                        "source": source,
                        "resolved": False,
                        "value_present": False,
                    }
            sidecar["outputs_matched"] = matched
            if resolved_outputs:
                sidecar["resolved_outputs"] = resolved_outputs

    acceptance_evidence = build_acceptance_evidence(
        playbook_code=playbook_code,
        result_data=result_data,
        resolved_outputs=sidecar.get("resolved_outputs"),
    )
    if acceptance_evidence:
        sidecar["acceptance_evidence"] = acceptance_evidence

    return sidecar


def resolve_source_path(data: Dict[str, Any], source: str) -> Any:
    """Resolve a dot-path source from a dictionary payload."""
    if not source or not isinstance(data, dict):
        return None
    parts = source.split(".")
    current: Any = data
    for part in parts:
        if isinstance(current, dict) and part in current:
            current = current[part]
        else:
            return None
    return current


def extract_context_attachments(result_data: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Extract evidence attachments from result payload and metadata."""
    candidates: List[Dict[str, Any]] = []

    direct = result_data.get("context_attachments")
    if isinstance(direct, list):
        candidates.extend(item for item in direct if isinstance(item, dict))

    metadata = result_data.get("metadata")
    if isinstance(metadata, dict):
        nested = metadata.get("context_attachments")
        if isinstance(nested, list):
            candidates.extend(item for item in nested if isinstance(item, dict))

    attachments = result_data.get("attachments")
    if isinstance(attachments, list):
        candidates.extend(item for item in attachments if isinstance(item, dict))

    deduped: List[Dict[str, Any]] = []
    seen = set()
    for item in candidates:
        key = json.dumps(item, sort_keys=True, default=str)
        if key in seen:
            continue
        seen.add(key)
        deduped.append(item)
    return deduped


def candidate_result_roots(
    result_data: Dict[str, Any],
    playbook_code: Optional[str],
) -> List[Dict[str, Any]]:
    """Return unique dictionaries that can contain declared output paths."""
    roots: List[Dict[str, Any]] = [result_data]
    steps = result_data.get("steps")
    if isinstance(steps, dict) and playbook_code:
        nested = steps.get(playbook_code)
        if isinstance(nested, dict):
            roots.append(nested)
    result_json = result_data.get("result_json")
    if isinstance(result_json, dict):
        roots.append(result_json)
        nested_steps = result_json.get("steps")
        if isinstance(nested_steps, dict) and playbook_code:
            nested = nested_steps.get(playbook_code)
            if isinstance(nested, dict):
                roots.append(nested)

    deduped: List[Dict[str, Any]] = []
    seen = set()
    for root in roots:
        root_id = id(root)
        if root_id in seen:
            continue
        seen.add(root_id)
        deduped.append(root)
    return deduped


def legacy_step_output_source(source: str) -> Optional[str]:
    """Return the legacy step output path for a step source path."""
    if isinstance(source, str) and source.startswith("step."):
        return f"step_outputs.{source[len('step.'):]}"
    return None


def resolve_output_value(
    *,
    roots: List[Dict[str, Any]],
    output_name: str,
    source: str,
) -> Any:
    """Resolve one declared output from candidate result roots."""
    candidate_paths: List[str] = []
    if isinstance(source, str) and source:
        candidate_paths.append(source)
        legacy_source = legacy_step_output_source(source)
        if legacy_source:
            candidate_paths.append(legacy_source)
    candidate_paths.append(f"outputs.{output_name}")

    for root in roots:
        if not isinstance(root, dict):
            continue
        for path in candidate_paths:
            value = resolve_source_path(root, path)
            if value is not None:
                return value
    return None


def has_material_value(value: Any) -> bool:
    """Return whether a value is present enough to include in evidence."""
    if value is None:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, (list, tuple, set, dict)):
        return len(value) > 0
    return True


def summarize_output_value(output_name: str, value: Any) -> Any:
    """Reduce resolved output values into provenance-safe summaries."""
    if not has_material_value(value):
        return None
    if output_name == "acceptance_evidence" and isinstance(value, dict):
        return dict(value)
    if isinstance(value, dict):
        filtered = {
            field_name: value[field_name]
            for field_name in (
                "session_id",
                "run_id",
                "status",
                "source_type",
            )
            if value.get(field_name) not in (None, "", [], {})
        }
        if filtered:
            return filtered
        return {"keys": sorted(value.keys())[:10]}
    if isinstance(value, list):
        return {"count": len(value)}
    return value


def build_acceptance_evidence(
    *,
    playbook_code: Optional[str],
    result_data: Dict[str, Any],
    resolved_outputs: Optional[Dict[str, Any]],
) -> Dict[str, Any]:
    """Build acceptance evidence from resolved outputs or result payload."""
    resolved_outputs = (
        dict(resolved_outputs)
        if isinstance(resolved_outputs, dict)
        else {}
    )
    direct = resolved_outputs.get("acceptance_evidence")
    if isinstance(direct, dict) and direct:
        evidence = dict(direct)
    else:
        direct = first_value(
            result_data,
            [
                "outputs.acceptance_evidence",
                "acceptance_evidence",
                "metadata.acceptance_evidence",
                "result_json.outputs.acceptance_evidence",
                "result_json.acceptance_evidence",
            ],
        )
        evidence = dict(direct) if isinstance(direct, dict) and direct else {}
    if evidence and playbook_code and not evidence.get("playbook_code"):
        evidence["playbook_code"] = playbook_code
    return evidence


def first_value(data: Dict[str, Any], paths: List[str]) -> Any:
    """Return the first material value found at one of the source paths."""
    for path in paths:
        value = resolve_source_path(data, path)
        if has_material_value(value):
            return value
    return None


def compute_hash(data: Any) -> Optional[str]:
    """Compute SHA-256 hash of serializable data."""
    try:
        serialized = json.dumps(data, sort_keys=True, default=str)
        return hashlib.sha256(serialized.encode("utf-8")).hexdigest()
    except Exception:
        return None
