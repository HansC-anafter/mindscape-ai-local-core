"""Compile request-contract data intents into a deterministic planner tool plan."""

from __future__ import annotations

import hashlib
import re
from typing import Any, Dict, Iterable, List, Optional

from backend.app.services.orchestration.meeting.planner_contract_execution.manifest_registry import (
    PlannerContractManifestRegistry,
)
from backend.app.services.orchestration.meeting.planner_contract_execution.tool_plan_models import (
    PlannerToolPlan,
    PlannerToolPlanCategory,
    PlannerToolPlanStep,
)


class PlannerToolPlanCompiler:
    """Build one MeetingEngine-scoped tool plan from installed planner contracts."""

    _MAX_CATEGORIES = 10

    def __init__(
        self,
        registry: Optional[PlannerContractManifestRegistry] = None,
    ) -> None:
        self.registry = registry or PlannerContractManifestRegistry()

    def compile(
        self,
        *,
        request_contract: Optional[Any],
        session_metadata: Optional[Dict[str, Any]],
        workspace_id: str,
        meeting_id: str,
    ) -> Optional[PlannerToolPlan]:
        """Return a complete executable plan, or None when the contract is out of scope."""
        metadata = session_metadata if isinstance(session_metadata, dict) else {}
        pack_id = self.registry.active_pack_id(metadata)
        if not pack_id:
            return None

        source_message = self._source_message(request_contract, metadata)
        if not self._is_creative_space_classification_request(source_message):
            return None

        category_labels = self._extract_category_labels(source_message)
        if not category_labels:
            return None

        planner_tools = self.registry.load_planner_tools_for_pack(pack_id)
        tool_seed = self._find_tool(
            planner_tools,
            resource_kind="seed",
            effect="read",
        )
        tool_query_refs = self._find_tool(
            planner_tools,
            resource_kind="reference",
            effect="read",
        )
        tool_create_space = self._find_tool(
            planner_tools,
            resource_kind="creative_space",
            effect="write",
        )
        tool_add_members = self._find_tool(
            planner_tools,
            resource_kind="creative_space_member",
            effect="write",
        )
        if not (tool_query_refs and tool_create_space and tool_add_members):
            return None

        digest = self._digest(
            {
                "workspace_id": workspace_id,
                "meeting_id": meeting_id,
                "pack_id": pack_id,
                "categories": category_labels,
            }
        )
        categories: List[PlannerToolPlanCategory] = []
        steps: List[PlannerToolPlanStep] = []
        for label in category_labels:
            category_id = f"cat_{self._digest({'label': label})[:10]}"
            idempotency_key = (
                f"meeting:{meeting_id}:creative_space:{self._digest({'label': label})[:16]}"
            )
            categories.append(
                PlannerToolPlanCategory(
                    category_id=category_id,
                    label=label,
                    description=(
                        f"Meeting-generated creative space for {label} seeds and references."
                    ),
                    idempotency_key=idempotency_key,
                )
            )

            role_step_ids: Dict[str, str] = {}
            if tool_seed:
                list_seed_step = self._build_step(
                    tool=tool_seed,
                    role="list_seeds",
                    category_id=category_id,
                    category_label=label,
                    arguments={
                        "workspace_id": workspace_id,
                        "query": label,
                        "limit": self._bounded_limit(tool_seed, default=200),
                    },
                )
                role_step_ids["list_seeds"] = list_seed_step.step_id
                steps.append(list_seed_step)

            query_refs_step = self._build_step(
                tool=tool_query_refs,
                role="query_references",
                category_id=category_id,
                category_label=label,
                arguments={
                    "workspace_id": workspace_id,
                    "query": label,
                    "limit": self._bounded_limit(tool_query_refs, default=100),
                },
            )
            role_step_ids["query_references"] = query_refs_step.step_id
            steps.append(query_refs_step)

            create_space_step = self._build_step(
                tool=tool_create_space,
                role="create_space",
                category_id=category_id,
                category_label=label,
                arguments={
                    "workspace_id": workspace_id,
                    "title": label,
                    "description": (
                        f"Meeting-generated creative space for {label} seeds and references."
                    ),
                    "idempotency_key": idempotency_key,
                    "metadata": {
                        "planner_contract": {
                            "meeting_id": meeting_id,
                            "category_id": category_id,
                            "category_label": label,
                        }
                    },
                },
            )
            role_step_ids["create_space"] = create_space_step.step_id
            steps.append(create_space_step)

            add_members_step = self._build_step(
                tool=tool_add_members,
                role="add_members",
                category_id=category_id,
                category_label=label,
                arguments={
                    "workspace_id": workspace_id,
                    "role": "reference",
                    "metadata": {
                        "planner_contract": {
                            "meeting_id": meeting_id,
                            "category_id": category_id,
                            "category_label": label,
                        }
                    },
                },
                depends_on=list(role_step_ids.values()),
                role_step_ids=role_step_ids,
            )
            steps.append(add_members_step)

        return PlannerToolPlan(
            plan_id=f"planner_tool_plan:{digest[:16]}",
            workspace_id=workspace_id,
            meeting_id=meeting_id,
            pack_id=pack_id,
            categories=categories,
            steps=steps,
            metadata={
                "source": "planner_contract_manifest",
                "source_message_hash": self._digest({"source_message": source_message})[:16],
                "category_count": len(categories),
                "step_count": len(steps),
            },
        )

    def _build_step(
        self,
        *,
        tool: Dict[str, Any],
        role: str,
        category_id: str,
        category_label: str,
        arguments: Dict[str, Any],
        depends_on: Optional[List[str]] = None,
        role_step_ids: Optional[Dict[str, str]] = None,
    ) -> PlannerToolPlanStep:
        contract = dict(tool.get("planner_contract") or {})
        hints = self._execution_hints(tool)
        step_id = f"{role}_{category_id}"
        return PlannerToolPlanStep(
            step_id=step_id,
            role=role,
            category_id=category_id,
            category_label=category_label,
            tool_name=str(tool.get("canonical_tool_name") or ""),
            resource_kind=str(contract.get("resource_kind") or ""),
            effect=str(contract.get("effect") or ""),
            arguments=arguments,
            input_bindings=self._scoped_input_bindings(
                hints.get("input_bindings"),
                role_step_ids or {},
            ),
            result_selectors={
                str(key): str(value)
                for key, value in dict(hints.get("result_selectors") or {}).items()
                if str(key or "").strip() and str(value or "").strip()
            },
            max_selector_fanout=self._bounded_limit(tool, default=200),
            depends_on=depends_on or [],
            planner_contract=contract,
        )

    def _find_tool(
        self,
        planner_tools: Iterable[Dict[str, Any]],
        *,
        resource_kind: str,
        effect: str,
    ) -> Optional[Dict[str, Any]]:
        for tool in planner_tools:
            contract = dict(tool.get("planner_contract") or {})
            if (
                str(contract.get("resource_kind") or "").strip() == resource_kind
                and str(contract.get("effect") or "").strip().lower() == effect
            ):
                return dict(tool)
        return None

    def _bounded_limit(self, tool: Dict[str, Any], *, default: int) -> int:
        hints = self._execution_hints(tool)
        raw_value = hints.get("max_selector_fanout", default)
        try:
            return max(1, min(int(raw_value), 500))
        except (TypeError, ValueError):
            return default

    def _execution_hints(self, tool: Dict[str, Any]) -> Dict[str, Any]:
        hints = tool.get("execution_hints")
        if isinstance(hints, dict):
            return dict(hints)
        contract = tool.get("planner_contract")
        if isinstance(contract, dict) and isinstance(contract.get("execution_hints"), dict):
            return dict(contract.get("execution_hints") or {})
        return {}

    def _scoped_input_bindings(
        self,
        raw_bindings: Any,
        role_step_ids: Dict[str, str],
    ) -> Dict[str, Any]:
        if not isinstance(raw_bindings, dict):
            return {}

        def _scope_expression(value: Any) -> Any:
            if isinstance(value, list):
                return [_scope_expression(item) for item in value]
            if not isinstance(value, str):
                return value
            scoped = value
            for role, step_id in role_step_ids.items():
                scoped = scoped.replace(f"$steps.{role}.", f"$steps.{step_id}.")
            return scoped

        return {str(key): _scope_expression(value) for key, value in raw_bindings.items()}

    def _source_message(
        self,
        request_contract: Optional[Any],
        session_metadata: Dict[str, Any],
    ) -> str:
        candidates: List[Any] = []
        if request_contract is not None:
            if hasattr(request_contract, "source_message"):
                candidates.append(getattr(request_contract, "source_message"))
            if hasattr(request_contract, "model_dump"):
                try:
                    candidates.append(request_contract.model_dump().get("source_message"))
                except Exception:
                    pass
            if isinstance(request_contract, dict):
                candidates.append(request_contract.get("source_message"))
        contract = session_metadata.get("request_contract")
        if isinstance(contract, dict):
            candidates.append(contract.get("source_message"))
        candidates.extend(
            [
                session_metadata.get("source_message"),
                session_metadata.get("meeting_command"),
            ]
        )
        for candidate in candidates:
            text = str(candidate or "").strip()
            if text:
                return text
        return ""

    def _is_creative_space_classification_request(self, source_message: str) -> bool:
        text = source_message.strip()
        if not text:
            return False
        lower = text.lower()
        has_creative_space = (
            "creative space" in lower
            or "creative_space" in lower
            or "creative spaces" in lower
            or "創意空間" in text
        )
        has_seed_or_ref = bool(
            re.search(r"\bseeds?\b|\brefs?\b|\breferences?\b|參考|素材", lower)
        )
        has_grouping = any(
            token in text
            for token in ("分門別類", "分類", "分組", "各新增", "新增")
        ) or any(token in lower for token in ("group", "categorize", "classify"))
        return has_creative_space and has_seed_or_ref and has_grouping

    def _extract_category_labels(self, source_message: str) -> List[str]:
        segments: List[str] = []
        patterns = [
            r"(?:跟|與|關於|針對)\s*(?P<items>[^。.!?\n]{1,120}?)(?:的\s*(?:seed|seeds|refs?|references?|參考|素材))",
            r"(?:把|將)\s*(?:所有|全部|當前|目前)?\s*(?:跟|與|關於|針對)?\s*(?P<items>[^。.!?\n]{1,120}?)(?:的\s*(?:seed|seeds|refs?|references?|參考|素材))",
            r"(?:categories?|分類|類別)\s*[:：]\s*(?P<items>[^。.!?\n]{1,120})",
        ]
        for pattern in patterns:
            for match in re.finditer(pattern, source_message, flags=re.IGNORECASE):
                segment = str(match.group("items") or "").strip()
                if segment:
                    segments.append(segment)

        labels: List[str] = []
        seen: set[str] = set()
        for segment in segments:
            normalized_segment = re.sub(r"\s*(?:及|和|與|and)\s*", "、", segment)
            for raw_part in re.split(r"[、,，/|]+", normalized_segment):
                label = self._normalize_category_label(raw_part)
                if not label:
                    continue
                key = label.casefold()
                if key in seen:
                    continue
                seen.add(key)
                labels.append(label)
                if len(labels) >= self._MAX_CATEGORIES:
                    return labels
        return labels

    def _normalize_category_label(self, raw_value: str) -> str:
        value = str(raw_value or "").strip(" \t\r\n'\"`[]()（）")
        while True:
            next_value = re.sub(
                r"^(所有|全部|當前|目前|跟|與|和|及|相關|about|current)\s*",
                "",
                value,
            )
            if next_value == value:
                break
            value = next_value
        value = re.sub(
            r"\s*(的)?\s*(seed|seeds|refs?|references?|參考|素材|相關)$",
            "",
            value,
            flags=re.IGNORECASE,
        )
        value = value.strip(" \t\r\n'\"`[]()（）")
        if not value or len(value) > 40:
            return ""
        if re.search(r"(creative\s+space|分門別類|新增|建立)", value, re.IGNORECASE):
            return ""
        return value

    def _digest(self, value: Any) -> str:
        import json

        return hashlib.sha256(
            json.dumps(value, ensure_ascii=False, sort_keys=True).encode("utf-8")
        ).hexdigest()
