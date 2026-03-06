#!/usr/bin/env python3
"""
Eval Runner for Capability Packs

Loads eval_config.yaml from installed capabilities and executes
tool_output scenarios. Reports results in text or JSON format.

Usage:
    python scripts/run_eval.py                          # all capabilities
    python scripts/run_eval.py --capability ig          # specific capability
    python scripts/run_eval.py --tags smoke             # filter by tag
    python scripts/run_eval.py --include-skipped        # include skip=true
    python scripts/run_eval.py --format json            # JSON output
"""

import argparse
import asyncio
import importlib
import inspect
import json
import re
import sys
import time
import traceback
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any, Dict, List, Optional


# Resolve project root (run_eval.py lives in scripts/)
PROJECT_ROOT = Path(__file__).resolve().parent.parent
CAPABILITIES_DIR = PROJECT_ROOT / "backend" / "app" / "capabilities"


# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------


@dataclass
class AssertionResult:
    """Result of a single assertion check."""

    field: str
    operator: str
    expected: Any
    actual: Any
    passed: bool
    message: str = ""


@dataclass
class CaseResult:
    """Result of a single test case."""

    case_index: int
    status: str  # pass, fail, error, skip
    duration_ms: float = 0.0
    assertions: List[AssertionResult] = field(default_factory=list)
    error: Optional[str] = None
    output: Optional[Any] = None


@dataclass
class ScenarioResult:
    """Result of a complete scenario."""

    name: str
    type: str
    capability: str
    status: str  # pass, fail, error, skip
    cases: List[CaseResult] = field(default_factory=list)
    skip_reason: Optional[str] = None
    error: Optional[str] = None


@dataclass
class EvalReport:
    """Aggregate report for an eval run."""

    total: int = 0
    passed: int = 0
    failed: int = 0
    errors: int = 0
    skipped: int = 0
    scenarios: List[ScenarioResult] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Assertion engine (aligned with eval_config.schema.yaml operators)
# ---------------------------------------------------------------------------


def resolve_jsonpath(data: Any, path: str) -> Any:
    """Simple JSONPath resolver for dot-notation and $. prefix."""
    if path.startswith("$."):
        path = path[2:]

    parts = path.split(".")
    current = data
    for part in parts:
        # Handle array index: e.g. items[0]
        match = re.match(r"^(\w+)\[(\d+)\]$", part)
        if match:
            key, idx = match.group(1), int(match.group(2))
            if isinstance(current, dict):
                current = current.get(key)
            if isinstance(current, (list, tuple)) and idx < len(current):
                current = current[idx]
            else:
                return None
        elif isinstance(current, dict):
            current = current.get(part)
        else:
            return None
    return current


def evaluate_assertion(output: Any, assertion: Dict[str, Any]) -> AssertionResult:
    """Evaluate a single assertion against tool output."""
    field_path = assertion["field"]
    operator = assertion["operator"]
    expected = assertion["value"]
    actual = resolve_jsonpath(output, field_path)

    passed = False
    message = ""

    try:
        if operator == "eq":
            passed = actual == expected
        elif operator == "neq":
            passed = actual != expected
        elif operator == "contains":
            passed = expected in actual if actual is not None else False
        elif operator == "not_contains":
            passed = expected not in actual if actual is not None else True
        elif operator == "gt":
            passed = actual > expected
        elif operator == "lt":
            passed = actual < expected
        elif operator == "gte":
            passed = actual >= expected
        elif operator == "lte":
            passed = actual <= expected
        elif operator == "matches":
            passed = (
                bool(re.search(expected, str(actual))) if actual is not None else False
            )
        elif operator == "type_is":
            type_map = {
                "string": str,
                "str": str,
                "int": int,
                "integer": int,
                "float": float,
                "number": (int, float),
                "bool": bool,
                "boolean": bool,
                "list": list,
                "array": list,
                "dict": dict,
                "object": dict,
                "none": type(None),
                "null": type(None),
            }
            expected_type = type_map.get(
                expected.lower() if isinstance(expected, str) else expected
            )
            if expected_type:
                passed = isinstance(actual, expected_type)
            else:
                message = f"Unknown type: {expected}"
        else:
            message = f"Unknown operator: {operator}"

        if not passed and not message:
            message = f"Expected {field_path} {operator} {expected!r}, got {actual!r}"

    except Exception as e:
        message = f"Assertion error: {e}"

    return AssertionResult(
        field=field_path,
        operator=operator,
        expected=expected,
        actual=actual,
        passed=passed,
        message=message,
    )


# ---------------------------------------------------------------------------
# Tool resolver
# ---------------------------------------------------------------------------


def load_manifest_tools(capability_code: str) -> Dict[str, Dict[str, Any]]:
    """Load tool definitions from a capability's manifest.yaml."""
    import yaml

    manifest_path = CAPABILITIES_DIR / capability_code / "manifest.yaml"
    if not manifest_path.exists():
        return {}

    with open(manifest_path) as f:
        manifest = yaml.safe_load(f) or {}

    tools = {}
    for tool in manifest.get("tools", []):
        if isinstance(tool, dict):
            name = tool.get("name", "")
            if name:
                tools[name] = tool
    return tools


def resolve_tool_backend(tool_def: Dict[str, Any]) -> Optional[callable]:
    """Dynamically import a tool function from its backend path."""
    backend = tool_def.get("backend", "")
    if not backend or ":" not in backend:
        return None

    module_path, func_name = backend.rsplit(":", 1)

    # In local-core installed context, capabilities are under backend.app.capabilities
    # Try the installed path first, then the raw capabilities path
    for prefix in ["backend.app.", ""]:
        full_module = f"{prefix}{module_path}"
        try:
            module = importlib.import_module(full_module)
            return getattr(module, func_name, None)
        except (ImportError, ModuleNotFoundError):
            continue

    return None


# ---------------------------------------------------------------------------
# Scenario executors
# ---------------------------------------------------------------------------


def run_tool_output_scenario(
    scenario: Dict[str, Any],
    capability_code: str,
    tools_map: Dict[str, Dict[str, Any]],
) -> ScenarioResult:
    """Execute a tool_output scenario."""
    name = scenario.get("name", "unknown")
    target_tool = scenario.get("target_tool", "")

    result = ScenarioResult(
        name=name,
        type="tool_output",
        capability=capability_code,
        status="pass",
    )

    # Resolve tool
    tool_def = tools_map.get(target_tool)
    if not tool_def:
        result.status = "error"
        result.error = f"Tool '{target_tool}' not found in manifest"
        return result

    tool_func = resolve_tool_backend(tool_def)
    if not tool_func:
        result.status = "error"
        result.error = f"Cannot import backend for '{target_tool}': {tool_def.get('backend', 'N/A')}"
        return result

    # Run cases
    output_config = scenario.get("output", {})
    cases = output_config.get("cases", [])

    for i, case in enumerate(cases):
        case_result = CaseResult(case_index=i, status="pass")
        tool_input = case.get("input", {})
        expected_status = case.get("expected_status", "success")

        start = time.monotonic()
        try:
            # Handle both sync and async tool functions
            if isinstance(tool_input, dict):
                raw = tool_func(**tool_input)
            else:
                raw = tool_func(tool_input)

            # Await coroutine if the tool is async
            if inspect.iscoroutine(raw):
                output = asyncio.run(raw)
            else:
                output = raw
            case_result.duration_ms = (time.monotonic() - start) * 1000

            # Check expected_status
            if expected_status == "error":
                case_result.status = "fail"
                case_result.error = "Expected error status but tool succeeded"
            else:
                case_result.output = output

                # Check expected_fields
                expected_fields = case.get("expected_fields", [])
                if expected_fields and isinstance(output, dict):
                    for ef in expected_fields:
                        if ef not in output:
                            ar = AssertionResult(
                                field=ef,
                                operator="exists",
                                expected=True,
                                actual=False,
                                passed=False,
                                message=f"Expected field '{ef}' missing from output",
                            )
                            case_result.assertions.append(ar)
                            case_result.status = "fail"

                # Run assertions
                for assertion_def in case.get("assertions", []):
                    ar = evaluate_assertion(output, assertion_def)
                    case_result.assertions.append(ar)
                    if not ar.passed:
                        case_result.status = "fail"

        except Exception as e:
            case_result.duration_ms = (time.monotonic() - start) * 1000
            if expected_status == "error":
                case_result.status = "pass"
            else:
                case_result.status = "error"
                case_result.error = f"{type(e).__name__}: {e}"

        result.cases.append(case_result)
        if case_result.status != "pass":
            result.status = case_result.status

    return result


# ---------------------------------------------------------------------------
# Main runner
# ---------------------------------------------------------------------------


def discover_eval_configs(
    capability_filter: Optional[str] = None,
) -> List[tuple]:
    """Discover eval_config.yaml files from installed capabilities."""
    import yaml

    configs = []
    if not CAPABILITIES_DIR.exists():
        return configs

    for cap_dir in sorted(CAPABILITIES_DIR.iterdir()):
        if not cap_dir.is_dir():
            continue
        if cap_dir.name.startswith("_") or cap_dir.name.startswith("."):
            continue
        if capability_filter and cap_dir.name != capability_filter:
            continue

        eval_config = cap_dir / "evals" / "eval_config.yaml"
        if not eval_config.exists():
            continue

        try:
            with open(eval_config) as f:
                config = yaml.safe_load(f)
            if config and isinstance(config, dict):
                configs.append((cap_dir.name, config))
        except Exception as e:
            print(f"WARNING: Failed to load {eval_config}: {e}", file=sys.stderr)

    return configs


def run_eval(
    capability_filter: Optional[str] = None,
    type_filter: Optional[str] = None,
    tag_filter: Optional[List[str]] = None,
    include_skipped: bool = False,
) -> EvalReport:
    """Run eval scenarios and return report."""
    report = EvalReport()
    configs = discover_eval_configs(capability_filter)

    if not configs:
        print("No eval configs found.", file=sys.stderr)
        return report

    for capability_code, config in configs:
        scenarios = config.get("scenarios", [])
        tools_map = load_manifest_tools(capability_code)

        for scenario in scenarios:
            if not isinstance(scenario, dict):
                continue

            name = scenario.get("name", "unknown")
            stype = scenario.get("type", "unknown")
            tags = scenario.get("tags", [])
            skip = scenario.get("skip", False)
            skip_reason = scenario.get("skip_reason", "")

            # Apply filters
            if type_filter and stype != type_filter:
                continue

            if tag_filter and not any(t in tags for t in tag_filter):
                continue

            report.total += 1

            # Handle skip
            if skip and not include_skipped:
                result = ScenarioResult(
                    name=name,
                    type=stype,
                    capability=capability_code,
                    status="skip",
                    skip_reason=skip_reason,
                )
                report.skipped += 1
                report.scenarios.append(result)
                continue

            # Dispatch by type
            if stype == "tool_output":
                result = run_tool_output_scenario(scenario, capability_code, tools_map)
            elif stype in ("tool_trigger", "playbook_flow", "integration"):
                result = ScenarioResult(
                    name=name,
                    type=stype,
                    capability=capability_code,
                    status="skip",
                    skip_reason=f"Type '{stype}' not yet supported (requires LLM runtime)",
                )
                report.skipped += 1
                report.scenarios.append(result)
                continue
            else:
                result = ScenarioResult(
                    name=name,
                    type=stype,
                    capability=capability_code,
                    status="error",
                    error=f"Unknown scenario type: {stype}",
                )

            # Tally
            if result.status == "pass":
                report.passed += 1
            elif result.status == "fail":
                report.failed += 1
            elif result.status == "error":
                report.errors += 1
            elif result.status == "skip":
                report.skipped += 1

            report.scenarios.append(result)

    return report


# ---------------------------------------------------------------------------
# Output formatters
# ---------------------------------------------------------------------------


def format_text(report: EvalReport) -> str:
    """Format report as human-readable text."""
    lines = []
    lines.append("=" * 60)
    lines.append("EVAL RESULTS")
    lines.append("=" * 60)

    for sr in report.scenarios:
        icon = {"pass": "✅", "fail": "❌", "error": "💥", "skip": "⏭️"}.get(
            sr.status, "?"
        )
        lines.append(f"  {icon} [{sr.capability}] {sr.name} ({sr.type})")

        if sr.skip_reason:
            lines.append(f"     Skip: {sr.skip_reason}")
        if sr.error:
            lines.append(f"     Error: {sr.error}")

        for cr in sr.cases:
            if cr.status != "pass":
                lines.append(
                    f"     Case {cr.case_index}: {cr.status} ({cr.duration_ms:.0f}ms)"
                )
                if cr.error:
                    lines.append(f"       {cr.error}")
                for ar in cr.assertions:
                    if not ar.passed:
                        lines.append(f"       ❌ {ar.message}")

    lines.append("")
    lines.append("-" * 60)
    lines.append(
        f"Total: {report.total}  "
        f"Passed: {report.passed}  "
        f"Failed: {report.failed}  "
        f"Errors: {report.errors}  "
        f"Skipped: {report.skipped}"
    )
    lines.append("=" * 60)

    return "\n".join(lines)


def format_json(report: EvalReport) -> str:
    """Format report as JSON."""
    data = asdict(report)
    return json.dumps(data, indent=2, default=str, ensure_ascii=False)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main():
    parser = argparse.ArgumentParser(description="Run capability eval scenarios")
    parser.add_argument("--capability", "-c", help="Filter by capability code")
    parser.add_argument(
        "--type", "-t", help="Filter by scenario type (e.g. tool_output)"
    )
    parser.add_argument("--tags", nargs="*", help="Filter by scenario tags")
    parser.add_argument(
        "--include-skipped", action="store_true", help="Include skipped scenarios"
    )
    parser.add_argument(
        "--format", choices=["text", "json"], default="text", help="Output format"
    )
    args = parser.parse_args()

    # Add project root to sys.path for imports
    if str(PROJECT_ROOT) not in sys.path:
        sys.path.insert(0, str(PROJECT_ROOT))

    report = run_eval(
        capability_filter=args.capability,
        type_filter=args.type,
        tag_filter=args.tags,
        include_skipped=args.include_skipped,
    )

    if args.format == "json":
        print(format_json(report))
    else:
        print(format_text(report))

    # Exit code: non-zero if any failures or errors
    if report.failed > 0 or report.errors > 0:
        sys.exit(1)


if __name__ == "__main__":
    main()
