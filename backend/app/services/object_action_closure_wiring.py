"""Runtime wiring for closing AOL object actions after tool execution."""

from __future__ import annotations

import logging
from typing import Any, Dict, Iterable, List, Optional

from backend.app.models.object_runtime import (
    ObjectActionClosureRequest,
    ObjectInstanceRecord,
    ObjectRelationRecord,
    ObjectRoleEntry,
)

logger = logging.getLogger(__name__)


def _as_dict(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _as_list(value: Any) -> List[Any]:
    return value if isinstance(value, list) else []


def _nested_dict(root: Dict[str, Any], path: Iterable[str]) -> Dict[str, Any]:
    current: Any = root
    for key in path:
        if not isinstance(current, dict):
            return {}
        current = current.get(key)
    return current if isinstance(current, dict) else {}


def _first_dict(*values: Any) -> Dict[str, Any]:
    for value in values:
        if isinstance(value, dict) and value:
            return value
    return {}


def _coerce_role_entries(raw_entries: Any) -> List[ObjectRoleEntry]:
    entries: List[ObjectRoleEntry] = []
    for raw_entry in _as_list(raw_entries):
        if not isinstance(raw_entry, dict):
            continue
        try:
            entries.append(ObjectRoleEntry(**raw_entry))
        except Exception:
            logger.debug("Ignoring malformed object action role entry", exc_info=True)
    return entries


def _coerce_output_records(raw_records: Any) -> List[ObjectInstanceRecord]:
    records: List[ObjectInstanceRecord] = []
    for raw_record in _as_list(raw_records):
        if not isinstance(raw_record, dict):
            continue
        try:
            records.append(ObjectInstanceRecord(**raw_record))
        except Exception:
            logger.debug("Ignoring malformed object action output record", exc_info=True)
    return records


def _coerce_output_relations(raw_relations: Any) -> List[ObjectRelationRecord]:
    relations: List[ObjectRelationRecord] = []
    for raw_relation in _as_list(raw_relations):
        if not isinstance(raw_relation, dict):
            continue
        try:
            relations.append(ObjectRelationRecord(**raw_relation))
        except Exception:
            logger.debug("Ignoring malformed object action output relation", exc_info=True)
    return relations


def _extract_plan_payload(inputs: Dict[str, Any]) -> Dict[str, Any]:
    plan_payload = _as_dict(inputs.get("object_action_plan"))
    request_plan = _as_dict(plan_payload.get("request_plan"))
    return _first_dict(request_plan, plan_payload)


def _extract_closure_payload(execution_result: Dict[str, Any]) -> Dict[str, Any]:
    """Find a structured AOL closure payload in common workflow result shapes."""

    direct = _as_dict(execution_result.get("object_action_closure"))
    outputs = _as_dict(execution_result.get("outputs"))
    result = _as_dict(execution_result.get("result"))
    workflow_result = _as_dict(execution_result.get("workflow_result"))

    return _first_dict(
        direct,
        _as_dict(outputs.get("object_action_closure")),
        _as_dict(result.get("object_action_closure")),
        _nested_dict(result, ("outputs", "object_action_closure")),
        _as_dict(workflow_result.get("object_action_closure")),
        _nested_dict(workflow_result, ("outputs", "object_action_closure")),
        _nested_dict(workflow_result, ("context", "object_action_closure")),
        _nested_dict(execution_result, ("context", "object_action_closure")),
    )


def _extract_output_records(
    execution_result: Dict[str, Any],
    closure_payload: Dict[str, Any],
) -> List[ObjectInstanceRecord]:
    outputs = _as_dict(execution_result.get("outputs"))
    result = _as_dict(execution_result.get("result"))
    workflow_result = _as_dict(execution_result.get("workflow_result"))
    candidates = [
        closure_payload.get("output_records"),
        closure_payload.get("object_action_outputs"),
        execution_result.get("output_records"),
        execution_result.get("object_action_outputs"),
        outputs.get("output_records"),
        outputs.get("object_action_outputs"),
        result.get("output_records"),
        result.get("object_action_outputs"),
        _nested_dict(result, ("outputs",)).get("output_records"),
        _nested_dict(result, ("outputs",)).get("object_action_outputs"),
        workflow_result.get("output_records"),
        workflow_result.get("object_action_outputs"),
        _nested_dict(workflow_result, ("outputs",)).get("output_records"),
        _nested_dict(workflow_result, ("outputs",)).get("object_action_outputs"),
    ]
    records: List[ObjectInstanceRecord] = []
    for candidate in candidates:
        records = _coerce_output_records(candidate)
        if records:
            return records
    return []


def _extract_output_relations(closure_payload: Dict[str, Any]) -> List[ObjectRelationRecord]:
    return _coerce_output_relations(
        closure_payload.get("output_relations") or closure_payload.get("relations")
    )


def close_object_action_from_execution_result(
    *,
    workspace_id: Optional[str],
    execution_id: Optional[str],
    inputs: Dict[str, Any],
    execution_result: Optional[Dict[str, Any]],
) -> Optional[Dict[str, Any]]:
    """Close an AOL action when runtime outputs provide durable object records.

    The runtime does not invent output objects. It only indexes closure payloads
    emitted by pack tools/playbooks and records a skipped state when a command
    carried an object-action plan but produced no addressable output records.
    """

    normalized_inputs = _as_dict(inputs)
    plan_payload = _extract_plan_payload(normalized_inputs)
    action_plan_id = str(
        normalized_inputs.get("object_action_plan_id")
        or plan_payload.get("action_plan_id")
        or ""
    ).strip()
    if not action_plan_id:
        return None

    result_payload = _as_dict(execution_result)
    closure_payload = _extract_closure_payload(result_payload)
    output_records = _extract_output_records(result_payload, closure_payload)
    if not output_records:
        return {
            "status": "skipped",
            "reason": "no_output_records",
            "action_plan_id": action_plan_id,
            "execution_id": execution_id,
        }

    if not workspace_id:
        return {
            "status": "failed",
            "reason": "missing_workspace_id",
            "action_plan_id": action_plan_id,
            "execution_id": execution_id,
        }

    entries = _coerce_role_entries(
        normalized_inputs.get("object_action_entries")
        or _as_dict(normalized_inputs.get("object_action_plan")).get("role_assignments")
    )
    affordance_payload = _as_dict(
        _as_dict(normalized_inputs.get("object_action_plan")).get("selected_affordance")
    )
    affordance_verb = str(
        closure_payload.get("affordance_verb")
        or normalized_inputs.get("affordance_verb")
        or plan_payload.get("affordance_verb")
        or affordance_payload.get("verb")
        or ""
    ).strip() or None
    meeting_id = str(
        closure_payload.get("meeting_id")
        or normalized_inputs.get("meeting_id")
        or normalized_inputs.get("meeting_session_id")
        or ""
    ).strip() or None

    status = str(closure_payload.get("status") or "succeeded").strip().lower()
    if status not in {"succeeded", "failed", "cancelled"}:
        status = "succeeded"

    close_request = ObjectActionClosureRequest(
        action_plan_id=action_plan_id,
        status=status,  # type: ignore[arg-type]
        entries=entries,
        output_records=output_records,
        output_relations=_extract_output_relations(closure_payload),
        meeting_id=meeting_id,
        affordance_verb=affordance_verb,
        execution_result={
            "execution_id": execution_id,
            "result": result_payload,
        },
    )

    try:
        from backend.app.routes.core.workspace.object_runtime import (
            _build_object_action_closure_relations,
            _get_object_instance_registry_store,
            _get_object_relation_registry_store,
        )

        indexed_output_count = _get_object_instance_registry_store().upsert_many(
            workspace_id,
            close_request.output_records,
        )
        relation_records = _build_object_action_closure_relations(
            workspace_id=workspace_id,
            request=close_request,
        )
        indexed_relation_count = _get_object_relation_registry_store().upsert_many(
            workspace_id,
            relation_records,
        )
    except Exception as exc:
        logger.exception(
            "AOL object action closure failed for action_plan_id=%s execution_id=%s",
            action_plan_id,
            execution_id,
        )
        return {
            "status": "failed",
            "reason": str(exc),
            "action_plan_id": action_plan_id,
            "execution_id": execution_id,
        }

    return {
        "status": status,
        "action_plan_id": action_plan_id,
        "execution_id": execution_id,
        "indexed_output_count": indexed_output_count,
        "indexed_relation_count": indexed_relation_count,
        "output_refs": [
            record.ref.model_dump(exclude_none=True)
            for record in close_request.output_records
        ],
        "relation_kinds": [record.relation_kind for record in relation_records],
    }
