"""Meeting-level planner tool-plan executor."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from backend.app.services.orchestration.meeting.planner_contract_execution.tool_plan_models import (
    PlannerToolPlan,
    PlannerToolPlanCategory,
    PlannerToolPlanStep,
)
from backend.app.services.tools.base import MindscapeTool
from backend.app.services.tools.schemas import (
    ToolCategory,
    ToolDangerLevel,
    ToolInputSchema,
    ToolMetadata,
    ToolSourceType,
)
from backend.app.services.unified_tool_executor import UnifiedToolExecutor


class ExecutePlannerToolPlanTool(MindscapeTool):
    """Execute one deterministic MeetingEngine planner tool plan."""

    TOOL_NAME = "meeting.execute_planner_tool_plan"

    def __init__(self) -> None:
        metadata = ToolMetadata(
            name=self.TOOL_NAME,
            description=(
                "Execute a deterministic meeting-level planner tool plan using "
                "installed capability planner_contract tools."
            ),
            input_schema=ToolInputSchema(
                type="object",
                properties={
                    "planner_tool_plan": {
                        "type": "object",
                        "description": "PlannerToolPlan payload produced by MeetingEngine.",
                    }
                },
                required=["planner_tool_plan"],
            ),
            category=ToolCategory.AUTOMATION,
            source_type=ToolSourceType.BUILTIN,
            provider="meeting",
            danger_level=ToolDangerLevel.MEDIUM,
            tags=["meeting", "planner_contract", "tool_plan"],
        )
        super().__init__(metadata)

    async def execute(self, planner_tool_plan: Dict[str, Any]) -> Dict[str, Any]:
        plan = PlannerToolPlan.model_validate(planner_tool_plan)
        executor = UnifiedToolExecutor()
        categories = {category.category_id: category for category in plan.categories}
        step_results: Dict[str, Dict[str, Any]] = {}
        step_reports: List[Dict[str, Any]] = []
        completed_count = 0

        for step in plan.steps:
            missing_dependencies = [
                dep_id for dep_id in step.depends_on if dep_id not in step_results
            ]
            if missing_dependencies:
                step_reports.append(
                    {
                        "step_id": step.step_id,
                        "tool_name": step.tool_name,
                        "category_label": step.category_label,
                        "status": "failed",
                        "error": (
                            "Missing dependency results: "
                            + ", ".join(missing_dependencies)
                        ),
                    }
                )
                return self._final_result(plan, "failed", step_reports, completed_count)

            if step.tool_name == self.TOOL_NAME:
                step_reports.append(
                    {
                        "step_id": step.step_id,
                        "tool_name": step.tool_name,
                        "category_label": step.category_label,
                        "status": "failed",
                        "error": "Recursive planner tool-plan execution is blocked.",
                    }
                )
                return self._final_result(plan, "failed", step_reports, completed_count)

            category = categories.get(step.category_id)
            arguments = self._arguments_for_step(
                step=step,
                category=category,
                step_results=step_results,
            )
            execution = await executor.execute_tool(step.tool_name, arguments)
            selected_results = self._select_results(
                execution.result,
                step.result_selectors,
                step.max_selector_fanout,
            )
            report = {
                "step_id": step.step_id,
                "role": step.role,
                "tool_name": step.tool_name,
                "category_id": step.category_id,
                "category_label": step.category_label,
                "resource_kind": step.resource_kind,
                "effect": step.effect,
                "status": "success" if execution.success else "failed",
                "selected_results": selected_results,
                "result": execution.result,
                "error": execution.error,
            }
            step_reports.append(report)
            step_results[step.step_id] = {
                "result": execution.result,
                "selected_results": selected_results,
                "report": report,
            }
            if not execution.success:
                return self._final_result(plan, "failed", step_reports, completed_count)
            completed_count += 1

        return self._final_result(plan, "success", step_reports, completed_count)

    def _arguments_for_step(
        self,
        *,
        step: PlannerToolPlanStep,
        category: Optional[PlannerToolPlanCategory],
        step_results: Dict[str, Dict[str, Any]],
    ) -> Dict[str, Any]:
        arguments = dict(step.arguments)
        for key, binding in step.input_bindings.items():
            resolved = self._resolve_binding(
                binding,
                category=category,
                step_results=step_results,
            )
            if resolved not in (None, "", [], {}):
                arguments[key] = resolved
        return arguments

    def _resolve_binding(
        self,
        binding: Any,
        *,
        category: Optional[PlannerToolPlanCategory],
        step_results: Dict[str, Dict[str, Any]],
    ) -> Any:
        if isinstance(binding, list):
            values: List[Any] = []
            for item in binding:
                resolved = self._resolve_binding(
                    item,
                    category=category,
                    step_results=step_results,
                )
                if isinstance(resolved, list):
                    values.extend(resolved)
                elif resolved not in (None, "", [], {}):
                    values.append(resolved)
            return self._dedupe(values)
        if not isinstance(binding, str):
            return binding
        if binding == "$category.label":
            return category.label if category else None
        if binding == "$category.description":
            return category.description if category else None
        if binding == "$category.idempotency_key":
            return category.idempotency_key if category else None
        prefix = "$steps."
        if not binding.startswith(prefix):
            return binding
        remainder = binding[len(prefix) :]
        step_id, separator, selector_path = remainder.partition(".result.")
        if not separator:
            return None
        previous = step_results.get(step_id)
        if not previous:
            return None
        selector_name = selector_path.strip()
        selected_results = previous.get("selected_results")
        if isinstance(selected_results, dict) and selector_name in selected_results:
            return selected_results.get(selector_name)
        raw_result = previous.get("result")
        return self._select_json_path(raw_result, f"$.{selector_name}", 500)

    def _select_results(
        self,
        result: Any,
        selectors: Dict[str, str],
        max_fanout: int,
    ) -> Dict[str, Any]:
        selected: Dict[str, Any] = {}
        for name, expression in selectors.items():
            selected[name] = self._select_json_path(result, expression, max_fanout)
        return selected

    def _select_json_path(self, data: Any, expression: str, max_fanout: int) -> Any:
        if not isinstance(expression, str) or not expression.startswith("$."):
            return None
        parts = [part for part in expression[2:].split(".") if part]
        values: List[Any] = [data]
        used_wildcard = False
        for part in parts:
            next_values: List[Any] = []
            if part.endswith("[*]"):
                used_wildcard = True
                key = part[:-3]
                for value in values:
                    if isinstance(value, dict):
                        candidate = value.get(key)
                    else:
                        candidate = None
                    if isinstance(candidate, list):
                        next_values.extend(candidate)
                values = next_values
                continue
            for value in values:
                if isinstance(value, dict):
                    next_values.append(value.get(part))
                elif isinstance(value, list):
                    for item in value:
                        if isinstance(item, dict):
                            next_values.append(item.get(part))
            values = next_values
        cleaned = [value for value in values if value not in (None, "", [], {})]
        if used_wildcard:
            return cleaned[: max(1, min(int(max_fanout or 1), 500))]
        if len(cleaned) == 1:
            return cleaned[0]
        return cleaned[: max(1, min(int(max_fanout or 1), 500))]

    def _dedupe(self, values: List[Any]) -> List[Any]:
        seen: set[str] = set()
        result: List[Any] = []
        for value in values:
            key = str(value)
            if key in seen:
                continue
            seen.add(key)
            result.append(value)
        return result

    def _final_result(
        self,
        plan: PlannerToolPlan,
        status: str,
        step_reports: List[Dict[str, Any]],
        completed_count: int,
    ) -> Dict[str, Any]:
        return {
            "status": status,
            "plan_id": plan.plan_id,
            "workspace_id": plan.workspace_id,
            "meeting_id": plan.meeting_id,
            "pack_id": plan.pack_id,
            "categories": [
                category.model_dump(mode="json") for category in plan.categories
            ],
            "plan_steps": step_reports,
            "completed_count": completed_count,
            "total_steps": len(plan.steps),
        }


def create_meeting_planner_tools() -> List[MindscapeTool]:
    """Return all builtin Meeting planner tools."""
    return [ExecutePlannerToolPlanTool()]
