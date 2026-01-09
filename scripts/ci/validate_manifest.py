#!/usr/bin/env python3
"""
CI Script: Validate Manifest Schema

Validates capability manifest.yaml against schema.

Requirements:
- portability field (required)
- environments must include local-core
- tool backend must use capabilities.* format (mindscape.capabilities.* is deprecated)
- API path must be under api/ directory

Usage:
    python scripts/ci/validate_manifest.py capabilities/
    python scripts/ci/validate_manifest.py --strict capabilities/example_capability
"""

import sys
import argparse
import re
import json
from pathlib import Path
from typing import List, Dict, Any, Tuple, Optional
from dataclasses import dataclass
import yaml

try:
    from jsonschema import validate, ValidationError as JsonSchemaValidationError
    JSON_SCHEMA_AVAILABLE = True
except ImportError:
    JSON_SCHEMA_AVAILABLE = False
    JsonSchemaValidationError = Exception


@dataclass
class ValidationError:
    """Validation error."""
    capability: str
    field: str
    message: str
    severity: str  # "error" | "warning"


@dataclass
class ValidationResult:
    """Validation result."""
    capability: str
    valid: bool
    errors: List[ValidationError]
    warnings: List[ValidationError]


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

    # Read manifest
    try:
        with open(manifest_path, 'r', encoding='utf-8') as f:
            manifest = yaml.safe_load(f)
    except Exception as e:
        return ValidationResult(
            capability=capability_code,
            valid=False,
            errors=[ValidationError(
                capability=capability_code,
                field="manifest.yaml",
                message=f"Failed to parse YAML: {e}",
                severity="error"
            )],
            warnings=[]
        )

    if not manifest:
        return ValidationResult(
            capability=capability_code,
            valid=False,
            errors=[ValidationError(
                capability=capability_code,
                field="manifest.yaml",
                message="Manifest is empty",
                severity="error"
            )],
            warnings=[]
        )

    # ========================================================================
    # JSON Schema Validation (Required)
    # ========================================================================

    if not JSON_SCHEMA_AVAILABLE:
        errors.append(ValidationError(
            capability=capability_code,
            field="manifest.yaml",
            message="jsonschema library not available. Install with: pip install jsonschema",
            severity="error"
        ))
    else:
        # Calculate schema path (relative to script location)
        script_dir = Path(__file__).parent  # scripts/ci/
        schema_path = script_dir.parent.parent / "schemas" / "manifest.schema.yaml"

        if not schema_path.exists():
            # Schema file missing is a warning, not an error (schema validation is optional)
            warnings.append(ValidationError(
                capability=capability_code,
                field="manifest.yaml",
                message=f"Schema file not found: {schema_path}. JSON Schema validation skipped.",
                severity="warning"
            ))
        else:
            try:
                with open(schema_path, 'r', encoding='utf-8') as f:
                    schema = yaml.safe_load(f)
                # Convert manifest to JSON format (required by jsonschema)
                manifest_json = json.loads(json.dumps(manifest))
                validate(instance=manifest_json, schema=schema)
            except JsonSchemaValidationError as e:
                # JSON Schema validation failure is a critical error
                errors.append(ValidationError(
                    capability=capability_code,
                    field="manifest.yaml",
                    message=f"JSON Schema validation failed: {e.message}",
                    severity="error"
                ))
            except Exception as e:
                # Schema loading failure is also an error
                errors.append(ValidationError(
                    capability=capability_code,
                    field="manifest.yaml",
                    message=f"Failed to load or validate JSON Schema: {e}",
                    severity="error"
                ))

    # ========================================================================
    # Required Field Validation (Manual checks as supplement)
    # ========================================================================

    required_fields = ['code', 'version']
    for field in required_fields:
        if field not in manifest:
            errors.append(ValidationError(
                capability=capability_code,
                field=field,
                message=f"Missing required field: '{field}'",
                severity="error"
            ))

    # ========================================================================
    # Portability Validation
    # ========================================================================

    if 'portability' not in manifest:
        errors.append(ValidationError(
            capability=capability_code,
            field="portability",
            message=(
                "Missing required field: 'portability'. "
                "Add portability declaration to support cross-environment deployment."
            ),
            severity="error"
        ))
    else:
        portability = manifest['portability']

        # min_local_core_version
        if 'min_local_core_version' not in portability:
            errors.append(ValidationError(
                capability=capability_code,
                field="portability.min_local_core_version",
                message="Missing required field: 'portability.min_local_core_version'",
                severity="error"
            ))

        # environments
        if 'environments' not in portability:
            errors.append(ValidationError(
                capability=capability_code,
                field="portability.environments",
                message="Missing 'portability.environments'. Must declare supported environments.",
                severity="error"
            ))
        else:
            environments = portability['environments']
            if not isinstance(environments, list):
                errors.append(ValidationError(
                    capability=capability_code,
                    field="portability.environments",
                    message="'environments' must be a list",
                    severity="error"
                ))
            elif 'local-core' not in environments:
                capability_type = manifest.get('type', 'feature')
                is_cloud_only_core = (
                    capability_type == 'core' and
                    manifest.get('cloud_only', False) is True
                )

                if not is_cloud_only_core:
                    errors.append(ValidationError(
                        capability=capability_code,
                        field="portability.environments",
                        message=(
                            "Capability must support 'local-core' environment "
                            "(unless type: core with cloud_only: true)."
                        ),
                        severity="error"
                    ))
                else:
                    warnings.append(ValidationError(
                        capability=capability_code,
                        field="portability.environments",
                        message=(
                            "cloud_only core capability: local-core not required "
                            "but verify business exemption."
                        ),
                        severity="warning"
                    ))

    # ========================================================================
    # Tool Backend Path Validation
    # ========================================================================

    tools = manifest.get('tools', [])
    for i, tool in enumerate(tools):
        if not isinstance(tool, dict):
            continue

        tool_name = tool.get('name', f'tool_{i}')
        backend = tool.get('backend', '')

        if backend:
            # Check if using capabilities.* format (mindscape.capabilities.* is deprecated)
            if backend.startswith('mindscape.capabilities.'):
                errors.append(ValidationError(
                    capability=capability_code,
                    field=f"tools[{tool_name}].backend",
                    message=(
                        f"Tool backend must use 'capabilities.*' format (mindscape.capabilities.* is deprecated), got: '{backend}'"
                    ),
                    severity="error"
                ))
            elif not backend.startswith('capabilities.'):
                errors.append(ValidationError(
                    capability=capability_code,
                    field=f"tools[{tool_name}].backend",
                    message=(
                        f"Tool backend must start with 'capabilities.', got: '{backend}'"
                    ),
                    severity="error"
                ))
            else:
                # Simple format check: capabilities.{capability}.{module}:{function}
                pattern = r"^capabilities\\.[a-z0-9_]+\\.[a-z0-9_.]+:[a-z0-9_]+$"
                if not re.match(pattern, backend):
                    warnings.append(ValidationError(
                        capability=capability_code,
                        field=f"tools[{tool_name}].backend",
                        message=(
                            f"Tool backend format looks invalid: '{backend}'. "
                            "Expected capabilities.{capability}.{module}:{function}"
                        ),
                        severity="warning"
                    ))

    # ========================================================================
    # API Path Validation
    # ========================================================================

    api_defs = manifest.get('apis')
    using_legacy_capabilities = False
    if api_defs is None:
        api_defs = manifest.get('capabilities', [])
        if api_defs:
            using_legacy_capabilities = True

    if using_legacy_capabilities:
        warnings.append(ValidationError(
            capability=capability_code,
            field="capabilities",
            message="Using deprecated field 'capabilities'. Rename to 'apis'.",
            severity="warning"
        ))

    for cap in api_defs or []:
        if not isinstance(cap, dict):
            continue

        cap_code = cap.get('code', 'unknown')
        path = cap.get('path', '')

        if path:
            # Check if under api/ directory
            if not path.startswith('api/'):
                errors.append(ValidationError(
                    capability=capability_code,
                    field=f"apis[{cap_code}].path",
                    message="API path must be under api/ directory.",
                    severity="error"
                ))

        if 'prefix' not in cap or not cap.get('prefix'):
            errors.append(ValidationError(
                capability=capability_code,
                field=f"apis[{cap_code}].prefix",
                message="Missing required field: 'prefix' (Option A rule).",
                severity="error"
            ))
        else:
            prefix = cap.get('prefix')
            # Prefix should be a valid URL path (can contain multiple segments)
            # Format: /api/v1/capabilities/{capability_code} or similar
            if not isinstance(prefix, str) or not prefix.startswith('/'):
                errors.append(ValidationError(
                    capability=capability_code,
                    field=f"apis[{cap_code}].prefix",
                    message=f"Invalid prefix format: '{prefix}'. Must be a string starting with '/'",
                    severity="error"
                ))
            elif not re.match(r"^/[a-z0-9_/]+$", str(prefix)):
                warnings.append(ValidationError(
                    capability=capability_code,
                    field=f"apis[{cap_code}].prefix",
                    message=f"Prefix format may be invalid: '{prefix}'. Should be a valid URL path",
                    severity="warning"
                ))

    # ========================================================================
    # UI Mode Validation (Phase 0.4)
    # ========================================================================

    ui_mode = manifest.get('ui_mode')
    if ui_mode is not None:
        valid_ui_modes = ['local-only', 'cloud-enhanced']
        if ui_mode not in valid_ui_modes:
            errors.append(ValidationError(
                capability=capability_code,
                field="ui_mode",
                message=(
                    f"Invalid ui_mode: '{ui_mode}'. "
                    f"Must be one of: {', '.join(valid_ui_modes)}"
                ),
                severity="error"
            ))
        else:
            # Phase 1: Default to local-only
            if ui_mode == 'cloud-enhanced':
                warnings.append(ValidationError(
                    capability=capability_code,
                    field="ui_mode",
                    message=(
                        "ui_mode='cloud-enhanced' is for Phase 2. "
                        "Phase 1 should use 'local-only'."
                    ),
                    severity="warning"
                ))

    cloud_compatible = manifest.get('cloud_compatible')
    if cloud_compatible is not None and not isinstance(cloud_compatible, bool):
        errors.append(ValidationError(
            capability=capability_code,
            field="cloud_compatible",
            message="cloud_compatible must be a boolean value.",
            severity="error"
        ))

    local_fallback = manifest.get('local_fallback')
    if local_fallback is not None:
        if not isinstance(local_fallback, bool):
            errors.append(ValidationError(
                capability=capability_code,
                field="local_fallback",
                message="local_fallback must be a boolean value.",
                severity="error"
            ))
        elif local_fallback and ui_mode != 'cloud-enhanced':
            warnings.append(ValidationError(
                capability=capability_code,
                field="local_fallback",
                message=(
                    "local_fallback is only relevant when ui_mode='cloud-enhanced'. "
                    "Consider removing or setting ui_mode='cloud-enhanced'."
                ),
                severity="warning"
            ))

    # ========================================================================
    # Dependencies Validation
    # ========================================================================

    dependencies = manifest.get('dependencies', {})

    # Check if optional dependencies have fallback or degraded_features
    optional_deps = dependencies.get('optional', [])
    for dep in optional_deps:
        if isinstance(dep, dict):
            dep_name = dep.get('name', 'unknown')
            if 'fallback' not in dep and 'degraded_features' not in dep:
                warnings.append(ValidationError(
                    capability=capability_code,
                    field=f"dependencies.optional[{dep_name}]",
                    message=(
                        f"Optional dependency '{dep_name}' should have 'fallback' or "
                        "'degraded_features' to handle unavailability."
                    ),
                    severity="warning"
                ))

    # ========================================================================
    # Return Results
    # ========================================================================

    return ValidationResult(
        capability=capability_code,
        valid=len(errors) == 0,
        errors=errors,
        warnings=warnings
    )


def validate_directory(directory: Path) -> List[ValidationResult]:
    """
    Validate manifests for all capabilities in directory.

    Args:
        directory: Directory path

    Returns:
        All validation results
    """
    results = []

    # If directory itself contains manifest.yaml
    manifest_path = directory / "manifest.yaml"
    if manifest_path.exists():
        results.append(validate_manifest(manifest_path))
        return results

    # Otherwise iterate subdirectories
    for cap_dir in directory.iterdir():
        if not cap_dir.is_dir():
            continue
        if cap_dir.name.startswith('_') or cap_dir.name.startswith('.'):
            continue

        manifest_path = cap_dir / "manifest.yaml"
        if manifest_path.exists():
            results.append(validate_manifest(manifest_path))

    return results


def format_results(results: List[ValidationResult], verbose: bool = False) -> str:
    """Format validation results."""
    lines = []

    total_errors = sum(len(r.errors) for r in results)
    total_warnings = sum(len(r.warnings) for r in results)
    valid_count = sum(1 for r in results if r.valid)

    lines.append(f"Manifest Validation Results:")
    lines.append(f"  Total: {len(results)} capabilities")
    lines.append(f"  Valid: {valid_count}")
    lines.append(f"  Errors: {total_errors}")
    lines.append(f"  Warnings: {total_warnings}")
    lines.append("")

    for result in results:
        if result.valid and not result.warnings:
            lines.append(f"[OK] {result.capability}: Valid")
        elif result.valid and result.warnings:
            lines.append(f"[WARN] {result.capability}: Valid with {len(result.warnings)} warning(s)")
            if verbose:
                for w in result.warnings:
                    lines.append(f"   [WARN] {w.field}: {w.message}")
        else:
            lines.append(f"[ERROR] {result.capability}: Invalid ({len(result.errors)} error(s))")
            for e in result.errors:
                lines.append(f"   [ERROR] {e.field}: {e.message}")
            if verbose:
                for w in result.warnings:
                    lines.append(f"   [WARN] {w.field}: {w.message}")

    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(
        description="Validate capability manifest.yaml files against schema"
    )
    parser.add_argument(
        "paths",
        nargs="+",
        type=Path,
        help="Paths to validate (capability directories)"
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Treat warnings as errors"
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Show all warnings"
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output in JSON format"
    )

    args = parser.parse_args()

    all_results = []

    for path in args.paths:
        if not path.exists():
            print(f"Warning: Path does not exist: {path}", file=sys.stderr)
            continue

        results = validate_directory(path)
        all_results.extend(results)

    if args.json:
        import json
        output = {
            "total": len(all_results),
            "valid": sum(1 for r in all_results if r.valid),
            "results": [
                {
                    "capability": r.capability,
                    "valid": r.valid,
                    "errors": [
                        {"field": e.field, "message": e.message}
                        for e in r.errors
                    ],
                    "warnings": [
                        {"field": w.field, "message": w.message}
                        for w in r.warnings
                    ]
                }
                for r in all_results
            ]
        }
        print(json.dumps(output, indent=2))
    else:
        print(format_results(all_results, verbose=args.verbose))

    # Exit code
    has_errors = any(not r.valid for r in all_results)
    has_warnings = any(r.warnings for r in all_results)

    if has_errors:
        sys.exit(1)
    elif has_warnings and args.strict:
        sys.exit(1)
    else:
        sys.exit(0)


if __name__ == "__main__":
    main()

