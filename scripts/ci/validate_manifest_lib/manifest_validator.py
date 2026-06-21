from pathlib import Path

from .manifest_io import (
    append_json_schema_validation,
    load_manifest_yaml,
    resolve_manifest_tool_schema_paths,
)
from .manual_rules import validate_manual_manifest_rules
from .models import ValidationResult


def validate_manifest(manifest_path: Path) -> ValidationResult:
    """
    Validate single manifest.yaml.

    Args:
        manifest_path: Path to manifest.yaml

    Returns:
        ValidationResult
    """
    capability_code = manifest_path.parent.name
    errors = []
    warnings = []

    manifest, early_result = load_manifest_yaml(manifest_path, capability_code)
    if early_result is not None:
        return early_result
    assert manifest is not None

    resolve_manifest_tool_schema_paths(manifest, manifest_path)
    append_json_schema_validation(manifest, capability_code, errors, warnings)
    validate_manual_manifest_rules(
        manifest,
        manifest_path,
        capability_code,
        errors,
        warnings,
    )

    return ValidationResult(
        capability=capability_code,
        valid=len(errors) == 0,
        errors=errors,
        warnings=warnings,
    )
