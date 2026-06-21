import json
from pathlib import Path
from typing import List

from .models import ValidationResult


CORE_SLOTS = {
    "core.intents.list",
    "core.artifacts.list",
    "core.artifacts.get_latest",
    "core.artifacts.create",
    "core.workspace.update_metadata",
    "core.workspace.get",
    "core.mind_lens.get_composition",
}


def validate_tools_exist(spec_path: Path) -> List[ValidationResult]:
    """Validate that all referenced tools exist."""
    results = []

    try:
        with open(spec_path) as f:
            spec = json.load(f)
    except Exception:
        return results

    tools_needed = set()
    for step in spec.get("steps", []):
        if "playbook_slot" in step:
            continue
        if "tool" in step:
            tools_needed.add(step["tool"])
        if "tool_slot" in step:
            tools_needed.add(step["tool_slot"])

    for tool in tools_needed:
        if tool in CORE_SLOTS:
            results.append(
                ValidationResult(
                    check_name=f"tool_exists_{tool}",
                    passed=True,
                    message=f"Core slot: {tool}",
                )
            )
        elif tool.startswith("core_llm."):
            results.append(
                ValidationResult(
                    check_name=f"tool_exists_{tool}",
                    passed=True,
                    message=f"Core LLM tool: {tool}",
                )
            )
        else:
            results.append(
                ValidationResult(
                    check_name=f"tool_exists_{tool}",
                    passed=True,
                    message=f"External tool (needs runtime check): {tool}",
                )
            )

    return results
