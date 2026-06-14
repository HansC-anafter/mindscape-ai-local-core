"""Bind Meeting TaskIR phases to installed planner_contract tools."""

from __future__ import annotations

import hashlib
import json
import logging
from typing import Any, Dict, Iterable, List, Optional

from backend.app.models.request_contract import RequestContract
from backend.app.services.orchestration.meeting.planner_contract_execution.manifest_registry import (
    PlannerContractManifestRegistry,
)
from backend.app.services.orchestration.meeting.planner_contract_execution.models import (
    PlannerContractBinding,
    PlannerContractEffect,
    PlannerDataOperation,
)

logger = logging.getLogger(__name__)

_ROLE_METADATA_KEYS = (
    "meeting_role_profile_code",
    "meeting_lane_code",
    "pack_role_name",
    "idempotency_scope",
    "resource_budget_class",
    "trace_id",
)


class PlannerContractBindingService:
    """Attach deterministic planner contract bindings to TaskIR phases."""

    def __init__(
        self,
        registry: Optional[PlannerContractManifestRegistry] = None,
    ) -> None:
        self.registry = registry or PlannerContractManifestRegistry()

    def bind_task_ir(
        self,
        *,
        task_ir: Any,
        request_contract: Optional[Any] = None,
        session_metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        phases = list(getattr(task_ir, "phases", None) or [])
        if not phases:
            return {"status": "empty", "bound_count": 0, "items": []}

        operations = self._normalize_operations(request_contract)
        planner_tools = self.registry.load_planner_tools(
            session_metadata=session_metadata,
            tool_names=[getattr(phase, "tool_name", None) for phase in phases],
        )
        if not planner_tools:
            return {
                "status": "no_contract_tools",
                "bound_count": 0,
                "items": [],
            }

        tool_index = self._build_tool_index(planner_tools)
        operation_by_id = {operation.id: operation for operation in operations}
        operation_by_tool = self._operation_index_by_tool(operations)

        items: List[Dict[str, Any]] = []
        for phase in phases:
            tool_name = str(getattr(phase, "tool_name", None) or "").strip()
            operation = self._operation_for_phase(
                phase=phase,
                operation_by_tool=operation_by_tool,
            )
            tool = self._resolve_tool(
                tool_name=tool_name,
                operation=operation,
                tool_index=tool_index,
            )
            if not tool:
                continue

            binding = self._build_binding(
                phase=phase,
                tool=tool,
                operation=operation_by_id.get(operation.id) if operation else None,
            )
            phase.tool_name = binding.tool_name
            phase.planner_contract_binding = binding
            items.append(
                {
                    "phase_id": getattr(phase, "id", ""),
                    "tool_name": binding.tool_name,
                    "resource_kind": binding.resource_kind,
                    "effect": binding.effect.value,
                    "approval_required": binding.approval_required,
                }
            )

        status = "bound" if items else "no_matching_phase"
        return {"status": status, "bound_count": len(items), "items": items}

    def _normalize_operations(self, request_contract: Optional[Any]) -> List[PlannerDataOperation]:
        if request_contract is None:
            return []
        if isinstance(request_contract, RequestContract):
            raw_operations = request_contract.data_operations
        elif isinstance(request_contract, dict):
            raw_operations = request_contract.get("data_operations") or []
        elif hasattr(request_contract, "data_operations"):
            raw_operations = getattr(request_contract, "data_operations") or []
        else:
            raw_operations = []

        operations: List[PlannerDataOperation] = []
        for index, raw in enumerate(raw_operations, start=1):
            payload = raw.model_dump() if hasattr(raw, "model_dump") else raw
            if not isinstance(payload, dict):
                continue
            effect = self._enum_value(payload.get("effect")).strip().lower()
            resource_kind = str(payload.get("resource_kind") or "").strip()
            if effect not in PlannerContractEffect._value2member_map_ or not resource_kind:
                continue
            query = payload.get("query")
            metadata = (
                payload.get("metadata")
                if isinstance(payload.get("metadata"), dict)
                else {}
            )
            operations.append(
                PlannerDataOperation(
                    id=str(payload.get("id") or f"OP{index}"),
                    resource_kind=resource_kind,
                    effect=PlannerContractEffect(effect),
                    tool_name=(
                        str(payload.get("tool_name")).strip()
                        if payload.get("tool_name")
                        else None
                    ),
                    query=query if isinstance(query, dict) else {},
                    target_object_kind=payload.get("target_object_kind"),
                    acceptance_condition=payload.get("acceptance_condition"),
                    metadata=metadata,
                    **self._role_metadata(metadata),
                )
            )
        return operations

    def _build_tool_index(self, planner_tools: Iterable[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
        index: Dict[str, Dict[str, Any]] = {}
        for tool in planner_tools:
            canonical = str(tool.get("canonical_tool_name") or "").strip()
            code = str(tool.get("tool_code") or "").strip()
            if canonical:
                index[canonical] = tool
            if code:
                index[code] = tool
        return index

    def _operation_index_by_tool(
        self,
        operations: Iterable[PlannerDataOperation],
    ) -> Dict[str, PlannerDataOperation]:
        index: Dict[str, PlannerDataOperation] = {}
        for operation in operations:
            if not operation.tool_name:
                continue
            index[operation.tool_name] = operation
            if "." in operation.tool_name:
                _pack, _sep, code = operation.tool_name.partition(".")
                if code:
                    index.setdefault(code, operation)
        return index

    def _operation_for_phase(
        self,
        *,
        phase: Any,
        operation_by_tool: Dict[str, PlannerDataOperation],
    ) -> Optional[PlannerDataOperation]:
        tool_name = str(getattr(phase, "tool_name", None) or "").strip()
        if tool_name and tool_name in operation_by_tool:
            return operation_by_tool[tool_name]
        if "." in tool_name:
            _pack, _sep, code = tool_name.partition(".")
            return operation_by_tool.get(code)
        return None

    def _resolve_tool(
        self,
        *,
        tool_name: str,
        operation: Optional[PlannerDataOperation],
        tool_index: Dict[str, Dict[str, Any]],
    ) -> Optional[Dict[str, Any]]:
        if tool_name and tool_name in tool_index:
            return tool_index[tool_name]
        if "." in tool_name:
            _pack, _sep, code = tool_name.partition(".")
            if code in tool_index:
                return tool_index[code]
        if operation and operation.tool_name:
            if operation.tool_name in tool_index:
                return tool_index[operation.tool_name]
            if "." in operation.tool_name:
                _pack, _sep, code = operation.tool_name.partition(".")
                if code in tool_index:
                    return tool_index[code]
        return None

    def _build_binding(
        self,
        *,
        phase: Any,
        tool: Dict[str, Any],
        operation: Optional[PlannerDataOperation],
    ) -> PlannerContractBinding:
        contract = dict(tool.get("planner_contract") or {})
        effect_value = str(contract.get("effect") or "").strip().lower()
        effect = (
            PlannerContractEffect(effect_value)
            if effect_value in PlannerContractEffect._value2member_map_
            else PlannerContractEffect.ACTION
        )
        canonical_tool_name = str(tool.get("canonical_tool_name") or "").strip()
        resource_kind = str(contract.get("resource_kind") or "").strip()
        binding_seed = {
            "phase_id": getattr(phase, "id", ""),
            "tool_name": canonical_tool_name,
            "operation_id": operation.id if operation else None,
            "meeting_role_profile_code": (
                operation.meeting_role_profile_code if operation else None
            ),
            "meeting_lane_code": operation.meeting_lane_code if operation else None,
        }
        digest = hashlib.sha256(
            json.dumps(binding_seed, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest()[:16]
        return PlannerContractBinding(
            binding_id=f"planner_contract:{digest}",
            data_operation_id=operation.id if operation else None,
            pack_id=str(tool.get("pack_id") or ""),
            tool_name=canonical_tool_name,
            tool_code=str(tool.get("tool_code") or ""),
            resource_kind=resource_kind,
            effect=effect,
            workspace_scoped=bool(contract.get("workspace_scoped", True)),
            input_schema=contract.get("input_schema"),
            output_schema=contract.get("output_schema"),
            pagination=(
                contract.get("pagination")
                if isinstance(contract.get("pagination"), dict)
                else None
            ),
            idempotency=contract.get("idempotency"),
            approval_required=effect
            in {
                PlannerContractEffect.WRITE,
                PlannerContractEffect.ACTION,
                PlannerContractEffect.DELETE,
            },
            audit_fields=[
                str(field)
                for field in list(contract.get("audit_fields") or [])
                if str(field or "").strip()
            ],
            **self._binding_role_metadata(operation),
            source=str(tool.get("manifest_path") or "installed_manifest"),
            contract=contract,
        )

    def _role_metadata(self, metadata: Dict[str, Any]) -> Dict[str, Optional[str]]:
        return {
            key: self._optional_string(metadata.get(key))
            for key in _ROLE_METADATA_KEYS
        }

    def _binding_role_metadata(
        self,
        operation: Optional[PlannerDataOperation],
    ) -> Dict[str, Optional[str]]:
        if operation is None:
            return {key: None for key in _ROLE_METADATA_KEYS}
        return {key: getattr(operation, key) for key in _ROLE_METADATA_KEYS}

    def _optional_string(self, value: Any) -> Optional[str]:
        text = str(value or "").strip()
        return text or None

    def _enum_value(self, value: Any) -> str:
        enum_value = getattr(value, "value", value)
        return str(enum_value or "")
