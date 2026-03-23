"""
Spec validation helpers for playbook installation.
"""

import json
from pathlib import Path
from typing import List


def validate_playbook_required_fields(spec_path: Path) -> List[str]:
    """Validate required fields in a playbook spec."""
    errors: List[str] = []
    try:
        with open(spec_path, "r", encoding="utf-8") as file:
            spec = json.load(file)

        required_model_fields = ["kind", "inputs", "outputs"]
        for field in required_model_fields:
            if field not in spec:
                errors.append(f"Missing required field (PlaybookJson model): '{field}'")
            elif field == "inputs" and not isinstance(spec.get(field), dict):
                errors.append("Field 'inputs' must be a dictionary")
            elif field == "outputs" and not isinstance(spec.get(field), dict):
                errors.append("Field 'outputs' must be a dictionary")

        core_fields = [
            "playbook_code",
            "version",
            "display_name",
            "description",
            "steps",
        ]
        for field in core_fields:
            if field not in spec:
                errors.append(f"Missing required field (core spec): '{field}'")
            elif field == "steps" and not isinstance(spec.get(field), list):
                errors.append("Field 'steps' must be a list")

        if "required_capabilities" not in spec:
            errors.append(
                "Missing 'required_capabilities' field (must declare capability dependencies)"
            )

        if "data_locality" not in spec:
            errors.append(
                "Missing 'data_locality' field (must declare data boundary: local_only and cloud_allowed)"
            )

        cloud_forbidden_fields = [
            "webhook_url",
            "webhook_auth",
            "bundle_id",
            "download_url",
            "checksum",
        ]
        for field in cloud_forbidden_fields:
            if field in spec:
                errors.append(
                    f"Forbidden cloud-specific field found: '{field}' (must not be in playbook spec)"
                )

        input_schema = spec.get("input_schema", {})
        if isinstance(input_schema, dict):
            properties = input_schema.get("properties", {})
            cloud_forbidden_inputs = [
                "tenant_id",
                "actor_id",
                "subject_user_id",
                "plan_id",
                "execution_id",
                "trace_id",
            ]
            for field in cloud_forbidden_inputs:
                if field in properties:
                    errors.append(
                        f"Forbidden cloud-specific field in input_schema: '{field}' (must not be in playbook input_schema)"
                    )

        return errors
    except json.JSONDecodeError as exc:
        return [f"Invalid JSON: {exc}"]
    except Exception as exc:
        return [f"Validation error: {exc}"]
