"""Product-semantic admission rules for workflow execution sandboxes."""

from dataclasses import dataclass
from typing import Any, Mapping


@dataclass(frozen=True)
class ExecutionSandboxAdmission:
    """Resolved sandbox requirement for one playbook execution."""

    required: bool
    reason: str


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def resolve_execution_sandbox_admission(
    *,
    playbook_json: Any,
) -> ExecutionSandboxAdmission:
    """Keep repository sandboxes away from declared browser-only workflows.

    A playbook is browser-only when its execution profile explicitly reserves a
    browser context and its input contract does not declare project context.
    All other and all incomplete contracts retain the historical sandbox path.
    """
    execution_profile = _mapping(getattr(playbook_json, "execution_profile", None))
    resource_requirements = _mapping(
        execution_profile.get("resource_requirements")
    )
    declared_inputs = _mapping(getattr(playbook_json, "inputs", None))

    resource_class = str(execution_profile.get("resource_class") or "").strip().lower()
    browser_contexts = resource_requirements.get("browser_contexts")
    try:
        reserves_browser_context = int(browser_contexts or 0) > 0
    except (TypeError, ValueError):
        reserves_browser_context = False

    if (
        resource_class == "browser"
        and reserves_browser_context
        and "project_id" not in declared_inputs
    ):
        return ExecutionSandboxAdmission(
            required=False,
            reason="dedicated_browser_context_without_project_contract",
        )

    return ExecutionSandboxAdmission(
        required=True,
        reason="default_repository_sandbox_contract",
    )


__all__ = [
    "ExecutionSandboxAdmission",
    "resolve_execution_sandbox_admission",
]
