import json
import os
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import yaml

from .contract_rules import _resolve_schema_path_guard
from .models import ValidationError, ValidationResult

try:
    from jsonschema import validate, ValidationError as JsonSchemaValidationError

    JSON_SCHEMA_AVAILABLE = True
except ImportError:
    JSON_SCHEMA_AVAILABLE = False
    JsonSchemaValidationError = Exception


def load_manifest_yaml(
    manifest_path: Path, capability_code: str
) -> Tuple[Optional[Dict[str, Any]], Optional[ValidationResult]]:
    try:
        with open(manifest_path, "r", encoding="utf-8") as f:
            manifest = yaml.safe_load(f)
    except Exception as e:
        return None, ValidationResult(
            capability=capability_code,
            valid=False,
            errors=[
                ValidationError(
                    capability=capability_code,
                    field="manifest.yaml",
                    message=f"Failed to parse YAML: {e}",
                    severity="error",
                )
            ],
            warnings=[],
        )

    if not manifest:
        return None, ValidationResult(
            capability=capability_code,
            valid=False,
            errors=[
                ValidationError(
                    capability=capability_code,
                    field="manifest.yaml",
                    message="Manifest is empty",
                    severity="error",
                )
            ],
            warnings=[],
        )
    return manifest, None


def resolve_manifest_tool_schema_paths(
    manifest: Dict[str, Any], manifest_path: Path
) -> None:
    try:
        from backend.app.services.manifest_utils import resolve_tool_schema_paths

        resolve_tool_schema_paths(manifest, manifest_path.parent)
    except ImportError:
        for tool in manifest.get("tools", []) or []:
            if not isinstance(tool, dict):
                continue
            schema_path = tool.get("schema_path")
            if schema_path and "input_schema" not in tool:
                schema_file, guard_error = _resolve_schema_path_guard(
                    manifest_path.parent, schema_path
                )
                if guard_error:
                    continue
                if schema_file and schema_file.exists():
                    with schema_file.open("r", encoding="utf-8") as schema_handle:
                        if schema_file.suffix == ".json":
                            tool["input_schema"] = json.load(schema_handle)
                        else:
                            tool["input_schema"] = yaml.safe_load(schema_handle)


def append_json_schema_validation(
    manifest: Dict[str, Any],
    capability_code: str,
    errors: List[ValidationError],
    warnings: List[ValidationError],
) -> None:
    if not JSON_SCHEMA_AVAILABLE:
        errors.append(
            ValidationError(
                capability=capability_code,
                field="manifest.yaml",
                message="jsonschema library not available. Install with: pip install jsonschema",
                severity="error",
            )
        )
        return

    script_dir = Path(__file__).resolve().parents[1]
    default_schema_path = script_dir.parent.parent / "schemas" / "manifest.schema.yaml"
    env_schema_path_str = os.environ.get("MANIFEST_SCHEMA_PATH", "")
    env_schema_path = (
        Path(env_schema_path_str).expanduser() if env_schema_path_str else None
    )
    cwd_schema_path = Path.cwd() / "schemas" / "manifest.schema.yaml"
    monorepo_schema_path = (
        Path.cwd() / "mindscape-ai-local-core" / "schemas" / "manifest.schema.yaml"
    )

    candidate_paths = [
        default_schema_path,
        env_schema_path,
        cwd_schema_path,
        monorepo_schema_path,
    ]
    schema_path = next(
        (path for path in candidate_paths if path and path.exists() and path.is_file()),
        None,
    )

    if not schema_path:
        searched_paths = [str(p) for p in candidate_paths if p and p != Path(".")]
        message = (
            f"Schema file not found in container (searched: {', '.join(searched_paths)}). "
            "Note: Schema may exist in local filesystem but not mounted into container. "
            "JSON Schema validation skipped (optional)."
        )
        warnings.append(
            ValidationError(
                capability=capability_code,
                field="manifest.yaml",
                message=message,
                severity="warning",
            )
        )
        return

    try:
        with open(schema_path, "r", encoding="utf-8") as f:
            schema = yaml.safe_load(f)
        manifest_json = json.loads(json.dumps(manifest))
        validate(instance=manifest_json, schema=schema)
    except JsonSchemaValidationError as e:
        errors.append(
            ValidationError(
                capability=capability_code,
                field="manifest.yaml",
                message=f"JSON Schema validation failed: {e.message}",
                severity="error",
            )
        )
    except Exception as e:
        errors.append(
            ValidationError(
                capability=capability_code,
                field="manifest.yaml",
                message=f"Failed to load or validate JSON Schema: {e}",
                severity="error",
            )
        )
