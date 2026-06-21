import json
from pathlib import Path
from typing import List

from .models import ValidationResult


def validate_spec_structure(spec_path: Path) -> List[ValidationResult]:
    """Validate playbook spec structure."""
    results = []

    if not spec_path.exists():
        results.append(
            ValidationResult(
                check_name="spec_file_exists",
                passed=False,
                message=f"Spec file not found: {spec_path}",
            )
        )
        return results

    try:
        with open(spec_path) as f:
            spec = json.load(f)
    except json.JSONDecodeError as e:
        results.append(
            ValidationResult(
                check_name="spec_json_valid",
                passed=False,
                message=f"Invalid JSON: {e}",
            )
        )
        return results

    results.append(
        ValidationResult(
            check_name="spec_json_valid", passed=True, message="JSON is valid"
        )
    )

    required_fields = ["playbook_code", "steps"]
    for field in required_fields:
        if field not in spec:
            results.append(
                ValidationResult(
                    check_name=f"spec_has_{field}",
                    passed=False,
                    message=f"Missing required field: {field}",
                )
            )
        else:
            results.append(
                ValidationResult(
                    check_name=f"spec_has_{field}",
                    passed=True,
                    message=f"Has {field}",
                )
            )

    steps = spec.get("steps", [])
    if not isinstance(steps, list):
        results.append(
            ValidationResult(
                check_name="spec_steps_is_list",
                passed=False,
                message="steps must be a list",
            )
        )
    elif len(steps) == 0:
        results.append(
            ValidationResult(
                check_name="spec_has_steps", passed=False, message="steps is empty"
            )
        )
    else:
        results.append(
            ValidationResult(
                check_name="spec_has_steps",
                passed=True,
                message=f"Has {len(steps)} steps",
            )
        )

        for i, step in enumerate(steps):
            step_id = step.get("id", f"step_{i}")

            if "id" not in step:
                results.append(
                    ValidationResult(
                        check_name=f"step_{i}_has_id",
                        passed=False,
                        message=f"Step {i} missing 'id'",
                    )
                )

            has_binding = (
                "tool" in step or "tool_slot" in step or "playbook_slot" in step
            )
            if not has_binding:
                results.append(
                    ValidationResult(
                        check_name=f"step_{step_id}_has_tool",
                        passed=False,
                        message=(
                            f"Step '{step_id}' missing 'tool', 'tool_slot', "
                            "or 'playbook_slot'"
                        ),
                    )
                )

            outputs = step.get("outputs", {})
            tool_slot = step.get("tool_slot", "")
            if tool_slot == "core.artifacts.create" and "artifact" not in outputs:
                results.append(
                    ValidationResult(
                        check_name=f"step_{step_id}_output_standard_critical",
                        passed=False,
                        message=(
                            f"Step '{step_id}' uses core.artifacts.create but "
                            "outputs doesn't have 'artifact'"
                        ),
                    )
                )

    forbidden_fields = [
        "tenant_id",
        "plan_id",
        "execution_id",
        "trace_id",
        "webhook_url",
        "webhook_auth",
        "bundle_id",
    ]
    for field in forbidden_fields:
        if field in spec:
            results.append(
                ValidationResult(
                    check_name=f"spec_no_cloud_field_{field}",
                    passed=False,
                    message=(
                        "Playbook spec should not contain cloud-only field: "
                        f"{field}"
                    ),
                )
            )

    return results
