"""Dependency checks for validation service."""

import os
from typing import Dict, List, Tuple


def validate_dependencies(manifest: Dict, tool_registry, result: Dict) -> None:
    """Run dependency verification."""
    if tool_registry:
        tool_ok, tool_errors, tool_warnings = verify_tool_dependencies(
            manifest,
            tool_registry,
        )
        result["validation_stages"]["tool_dependencies"] = {
            "ok": tool_ok,
            "errors": tool_errors,
            "warnings": tool_warnings,
        }
        result["warnings"].extend(tool_warnings)

    api_ok, api_errors, api_warnings = check_api_keys(manifest)
    result["validation_stages"]["api_keys"] = {
        "ok": api_ok,
        "errors": api_errors,
        "warnings": api_warnings,
    }
    result["warnings"].extend(api_warnings)


def verify_tool_dependencies(
    manifest: Dict,
    tool_registry,
) -> Tuple[bool, List[str], List[str]]:
    """Verify tool dependencies."""
    errors = []
    warnings = []

    playbooks = manifest.get("playbooks", [])
    for playbook in playbooks:
        tool_deps = playbook.get("tool_dependencies", [])
        for tool_dep in tool_deps:
            if tool_dep.startswith("core_llm."):
                continue

            if hasattr(tool_registry, "has_tool"):
                if not tool_registry.has_tool(tool_dep):
                    warnings.append(f"Tool dependency not found: {tool_dep}")

    return len(errors) == 0, errors, warnings


def check_api_keys(manifest: Dict) -> Tuple[bool, List[str], List[str]]:
    """Check required API keys."""
    errors = []
    warnings = []

    required_api_keys = manifest.get("required_api_keys", [])
    for key_name in required_api_keys:
        env_var = os.getenv(key_name)
        if not env_var:
            warnings.append(f"Required API key not configured: {key_name}")

    return len(errors) == 0, errors, warnings
