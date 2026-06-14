"""Compile request-contract data intents into a deterministic planner tool plan."""

from __future__ import annotations

import hashlib
import os
import re
from typing import Any, Dict, Iterable, List, Optional

from backend.app.services.orchestration.meeting.role_profiles import (
    MeetingRoleProfileResolver,
)
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
        role_profile_resolver: Optional[MeetingRoleProfileResolver] = None,
    ) -> None:
        self.registry = registry or PlannerContractManifestRegistry()
        self.role_profile_resolver = role_profile_resolver or MeetingRoleProfileResolver()

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

        declarative_plan = self._compile_declarative_lane_if_enabled(
            request_contract=request_contract,
            session_metadata=metadata,
            workspace_id=workspace_id,
            meeting_id=meeting_id,
            pack_id=pack_id,
        )
        if declarative_plan is not None:
            return declarative_plan

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
        meeting_role_profile_code: Optional[str] = None,
        meeting_lane_code: Optional[str] = None,
        pack_role_name: Optional[str] = None,
        resource_budget_class: Optional[str] = None,
        trace_id: Optional[str] = None,
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
            meeting_role_profile_code=meeting_role_profile_code,
            meeting_lane_code=meeting_lane_code,
            pack_role_name=pack_role_name,
            resource_budget_class=resource_budget_class,
            trace_id=trace_id,
        )

    def _compile_declarative_lane_if_enabled(
        self,
        *,
        request_contract: Optional[Any],
        session_metadata: Dict[str, Any],
        workspace_id: str,
        meeting_id: str,
        pack_id: str,
    ) -> Optional[PlannerToolPlan]:
        if not (
            self._flag_enabled("MEETING_ROLE_PROFILES_ENABLED")
            and self._flag_enabled("DECLARATIVE_PLANNER_LANE_ENABLED")
            and self._pack_enabled_for_role_profiles(pack_id)
        ):
            return None

        selected_profile = self.role_profile_resolver.resolve(
            session_metadata=session_metadata,
            request_contract=request_contract,
        )
        if selected_profile is None or not selected_profile.planner_lane:
            return None

        planner_tools = self.registry.load_planner_tools_for_pack(pack_id)
        lane = dict(selected_profile.planner_lane)
        categories = self._declarative_lane_categories(
            lane=lane,
            selected_profile=selected_profile,
        )
        steps = self._declarative_lane_steps(
            lane=lane,
            selected_profile=selected_profile,
            planner_tools=planner_tools,
            categories=categories,
            workspace_id=workspace_id,
            meeting_id=meeting_id,
            session_metadata=session_metadata,
        )
        if not categories or not steps:
            return None

        digest = self._digest(
            {
                "workspace_id": workspace_id,
                "meeting_id": meeting_id,
                "pack_id": pack_id,
                "profile": selected_profile.code,
                "lane": selected_profile.meeting_lane_code,
                "categories": [category.model_dump(mode="json") for category in categories],
                "steps": [step.step_id for step in steps],
            }
        )
        return PlannerToolPlan(
            plan_id=f"planner_tool_plan:{digest[:16]}",
            workspace_id=workspace_id,
            meeting_id=meeting_id,
            pack_id=pack_id,
            categories=categories,
            steps=steps,
            metadata={
                "source": "meeting_role_profile_planner_lane",
                "meeting_role_profile_code": selected_profile.code,
                "meeting_lane_code": selected_profile.meeting_lane_code,
                "category_count": len(categories),
                "step_count": len(steps),
                "resource_governance": {
                    "workspace_scoped_required": True,
                    "read_bound_required": True,
                    "write_idempotency_required": True,
                    "polling_steps_allowed": False,
                    "world_memory_write_allowed": False,
                },
            },
        )

    def _declarative_lane_categories(
        self,
        *,
        lane: Dict[str, Any],
        selected_profile: Any,
    ) -> List[PlannerToolPlanCategory]:
        raw_categories = lane.get("categories")
        if not isinstance(raw_categories, list):
            raw_categories = []
        context = (
            selected_profile.selection_context.get("context")
            if isinstance(selected_profile.selection_context, dict)
            else {}
        )
        if not raw_categories:
            raw_categories = [
                {
                    "category_id": selected_profile.code,
                    "label": selected_profile.display_name,
                }
            ]

        categories: List[PlannerToolPlanCategory] = []
        for raw in raw_categories:
            if not isinstance(raw, dict):
                continue
            raw_label = raw.get("label")
            if not raw_label and raw.get("label_selector"):
                raw_label = self._resolve_selector(raw.get("label_selector"), context)
            label = str(raw_label or selected_profile.display_name or "").strip()
            if not label:
                continue
            category_id = str(raw.get("category_id") or "").strip()
            if not category_id:
                category_id = f"cat_{self._digest({'label': label})[:10]}"
            idempotency_key = str(raw.get("idempotency_key") or "").strip()
            if not idempotency_key:
                idempotency_key = (
                    "meeting:"
                    f"{selected_profile.code}:{category_id}:"
                    f"{self._digest({'label': label})[:16]}"
                )
            categories.append(
                PlannerToolPlanCategory(
                    category_id=category_id,
                    label=label,
                    description=str(raw.get("description") or "").strip(),
                    idempotency_key=idempotency_key,
                )
            )
        return categories

    def _declarative_lane_steps(
        self,
        *,
        lane: Dict[str, Any],
        selected_profile: Any,
        planner_tools: Iterable[Dict[str, Any]],
        categories: List[PlannerToolPlanCategory],
        workspace_id: str,
        meeting_id: str,
        session_metadata: Dict[str, Any],
    ) -> List[PlannerToolPlanStep]:
        raw_steps = lane.get("steps")
        if not isinstance(raw_steps, list):
            return []

        steps: List[PlannerToolPlanStep] = []
        for category in categories:
            role_step_ids: Dict[str, str] = {}
            for raw_step in raw_steps:
                if not isinstance(raw_step, dict):
                    continue
                step_code = str(raw_step.get("step_code") or "").strip()
                resource_kind = str(raw_step.get("resource_kind") or "").strip()
                effect = str(raw_step.get("effect") or "").strip().lower()
                if not step_code or not resource_kind or not effect:
                    continue
                tool = self._find_tool(
                    planner_tools,
                    resource_kind=resource_kind,
                    effect=effect,
                )
                if tool is None:
                    raise ValueError(
                        "Declarative planner lane step has no matching "
                        f"planner_contract tool: {resource_kind}/{effect}"
                    )
                self._validate_declarative_lane_tool(
                    tool=tool,
                    resource_kind=resource_kind,
                    effect=effect,
                    step_code=step_code,
                )

                arguments = self._declarative_step_arguments(
                    raw_step=raw_step,
                    category=category,
                    workspace_id=workspace_id,
                    meeting_id=meeting_id,
                    selected_profile=selected_profile,
                )
                depends_on = [
                    role_step_ids[dependency]
                    for dependency in self._string_list(raw_step.get("depends_on"))
                    if dependency in role_step_ids
                ]
                step = self._build_step(
                    tool=tool,
                    role=step_code,
                    category_id=category.category_id,
                    category_label=category.label,
                    arguments=arguments,
                    depends_on=depends_on,
                    role_step_ids=role_step_ids,
                    meeting_role_profile_code=selected_profile.code,
                    meeting_lane_code=selected_profile.meeting_lane_code,
                    pack_role_name=self._step_pack_role_name(raw_step, selected_profile),
                    resource_budget_class=self._optional_string(
                        raw_step.get("resource_budget_class")
                        or session_metadata.get("resource_budget_class")
                    ),
                    trace_id=self._optional_string(
                        raw_step.get("trace_id") or session_metadata.get("trace_id")
                    ),
                )
                role_step_ids[step_code] = step.step_id
                steps.append(step)
        return steps

    def _declarative_step_arguments(
        self,
        *,
        raw_step: Dict[str, Any],
        category: PlannerToolPlanCategory,
        workspace_id: str,
        meeting_id: str,
        selected_profile: Any,
    ) -> Dict[str, Any]:
        raw_arguments = raw_step.get("arguments")
        context = (
            selected_profile.selection_context.get("context")
            if isinstance(selected_profile.selection_context, dict)
            else {}
        )
        arguments = self._resolve_declarative_value(
            dict(raw_arguments) if isinstance(raw_arguments, dict) else {},
            category=category,
            context=context,
        )
        arguments.setdefault("workspace_id", workspace_id)
        arguments.setdefault("category_label", category.label)
        arguments.setdefault("idempotency_key", category.idempotency_key)
        metadata = dict(arguments.get("metadata") or {})
        planner_metadata = dict(metadata.get("planner_contract") or {})
        planner_metadata.update(
            {
                "meeting_id": meeting_id,
                "category_id": category.category_id,
                "category_label": category.label,
                "meeting_role_profile_code": selected_profile.code,
                "meeting_lane_code": selected_profile.meeting_lane_code,
            }
        )
        metadata["planner_contract"] = planner_metadata
        arguments["metadata"] = metadata
        return arguments

    def _validate_declarative_lane_tool(
        self,
        *,
        tool: Dict[str, Any],
        resource_kind: str,
        effect: str,
        step_code: str,
    ) -> None:
        contract = dict(tool.get("planner_contract") or {})
        hints = self._execution_hints(tool)
        if contract.get("workspace_scoped") is not True:
            raise ValueError(
                f"Declarative planner lane step {step_code} requires workspace_scoped=true"
            )
        if self._has_polling_hint(contract) or self._has_polling_hint(hints):
            raise ValueError(
                f"Declarative planner lane step {step_code} must not declare polling"
            )
        if self._is_world_memory_write(resource_kind=resource_kind, effect=effect):
            raise ValueError(
                f"Declarative planner lane step {step_code} must not write world memory"
            )
        if effect == "read":
            has_pagination = isinstance(contract.get("pagination"), dict)
            has_fanout_bound = hints.get("max_selector_fanout") is not None
            if not (has_pagination or has_fanout_bound):
                raise ValueError(
                    f"Declarative planner lane read step {step_code} needs pagination or fanout bound"
                )
        if effect in {"write", "action", "delete"}:
            idempotency = str(contract.get("idempotency") or "").strip().lower()
            if not idempotency or idempotency == "none":
                raise ValueError(
                    f"Declarative planner lane mutating step {step_code} needs idempotency"
                )

    def _step_pack_role_name(
        self,
        raw_step: Dict[str, Any],
        selected_profile: Any,
    ) -> Optional[str]:
        explicit = self._optional_string(raw_step.get("pack_role_name"))
        if explicit:
            return explicit
        slot = self._optional_string(raw_step.get("slot"))
        if slot:
            overrides = selected_profile.slot_overrides.get(slot)
            if isinstance(overrides, dict):
                return self._optional_string(overrides.get("pack_role_name"))
        return None

    def _resolve_selector(self, selector: Any, context: Any) -> Any:
        value = str(selector or "").strip()
        if not value.startswith("$context."):
            return None
        current: Any = context if isinstance(context, dict) else {}
        for part in value.removeprefix("$context.").split("."):
            if not isinstance(current, dict):
                return None
            current = current.get(part)
        if isinstance(current, str):
            text = current.strip()
            return text or None
        return current

    def _resolve_declarative_value(
        self,
        value: Any,
        *,
        category: PlannerToolPlanCategory,
        context: Any,
    ) -> Any:
        if isinstance(value, dict):
            return {
                str(key): self._resolve_declarative_value(
                    item,
                    category=category,
                    context=context,
                )
                for key, item in value.items()
            }
        if isinstance(value, list):
            return [
                self._resolve_declarative_value(
                    item,
                    category=category,
                    context=context,
                )
                for item in value
            ]
        if not isinstance(value, str):
            return value
        if value == "$category.label":
            return category.label
        if value == "$category.description":
            return category.description
        if value == "$category.idempotency_key":
            return category.idempotency_key
        if value.startswith("$context."):
            return self._resolve_selector(value, context)
        return value

    def _flag_enabled(self, name: str) -> bool:
        return str(os.getenv(name, "")).strip().lower() in {"1", "true", "yes", "on"}

    def _pack_enabled_for_role_profiles(self, pack_id: str) -> bool:
        raw_codes = str(os.getenv("MEETING_ROLE_PROFILES_ENABLED_PACK_CODES", "")).strip()
        if not raw_codes:
            return True
        return pack_id in {code.strip() for code in raw_codes.split(",") if code.strip()}

    def _has_polling_hint(self, payload: Dict[str, Any]) -> bool:
        return any(
            key in payload
            for key in (
                "polling",
                "polling_interval",
                "polling_interval_ms",
                "poll_interval",
                "poll_interval_ms",
            )
        )

    def _is_world_memory_write(self, *, resource_kind: str, effect: str) -> bool:
        if effect == "read":
            return False
        value = resource_kind.strip().lower()
        return value.startswith("world_memory") or value in {
            "world_card_projection",
            "world_memory_packet",
            "canonical_memory_item",
        }

    def _optional_string(self, value: Any) -> Optional[str]:
        text = str(value or "").strip()
        return text or None

    def _string_list(self, value: Any) -> List[str]:
        if isinstance(value, str):
            values = [value]
        elif isinstance(value, list):
            values = value
        else:
            values = []
        return [str(item).strip() for item in values if str(item or "").strip()]

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
