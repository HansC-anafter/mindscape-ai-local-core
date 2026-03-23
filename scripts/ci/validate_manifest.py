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
import os
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


def _resolve_schema_path_guard(
    base_dir: Path, schema_path_str: str
) -> Tuple[Optional[Path], Optional[str]]:
    """Resolve schema_path and block absolute/traversal paths."""
    schema_path = Path(schema_path_str)
    if schema_path.is_absolute():
        return None, f"Absolute schema_path is not allowed: {schema_path_str}"

    base_root = base_dir.resolve()
    resolved = (base_root / schema_path).resolve()
    try:
        resolved.relative_to(base_root)
    except ValueError:
        return None, f"schema_path escapes pack directory: {schema_path_str}"
    return resolved, None


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
        with open(manifest_path, "r", encoding="utf-8") as f:
            manifest = yaml.safe_load(f)
    except Exception as e:
        return ValidationResult(
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
        return ValidationResult(
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

    # Resolve schema_path references before any downstream validation
    try:
        from backend.app.services.manifest_utils import resolve_tool_schema_paths

        resolve_tool_schema_paths(manifest, manifest_path.parent)
    except ImportError:
        # CI may run outside the backend package context; inline resolution
        import json as _json

        for _tool in manifest.get("tools", []) or []:
            if not isinstance(_tool, dict):
                continue
            _sp = _tool.get("schema_path")
            if _sp and "input_schema" not in _tool:
                _sf, _guard_error = _resolve_schema_path_guard(
                    manifest_path.parent, _sp
                )
                if _guard_error:
                    continue
                if _sf and _sf.exists():
                    with _sf.open("r", encoding="utf-8") as _f:
                        if _sf.suffix == ".json":
                            _tool["input_schema"] = _json.load(_f)
                        else:
                            _tool["input_schema"] = yaml.safe_load(_f)

    # ========================================================================
    # JSON Schema Validation (Required)
    # ========================================================================

    if not JSON_SCHEMA_AVAILABLE:
        errors.append(
            ValidationError(
                capability=capability_code,
                field="manifest.yaml",
                message="jsonschema library not available. Install with: pip install jsonschema",
                severity="error",
            )
        )
    else:
        # Calculate schema path (relative to script location), with fallbacks
        script_dir = Path(__file__).parent  # scripts/ci/
        default_schema_path = (
            script_dir.parent.parent / "schemas" / "manifest.schema.yaml"
        )
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
        # Filter out None and non-file paths (e.g., directories)
        schema_path = next(
            (
                path
                for path in candidate_paths
                if path and path.exists() and path.is_file()
            ),
            None,
        )

        if not schema_path:
            # Schema file missing is a warning, not an error (schema validation is optional)
            # Note: Schema file may exist in local filesystem but not in Docker container
            # This is expected if schemas/ directory is not mounted into container
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
        else:
            try:
                with open(schema_path, "r", encoding="utf-8") as f:
                    schema = yaml.safe_load(f)
                # Convert manifest to JSON format (required by jsonschema)
                manifest_json = json.loads(json.dumps(manifest))
                validate(instance=manifest_json, schema=schema)
            except JsonSchemaValidationError as e:
                # JSON Schema validation failure is a critical error
                errors.append(
                    ValidationError(
                        capability=capability_code,
                        field="manifest.yaml",
                        message=f"JSON Schema validation failed: {e.message}",
                        severity="error",
                    )
                )
            except Exception as e:
                # Schema loading failure is also an error
                errors.append(
                    ValidationError(
                        capability=capability_code,
                        field="manifest.yaml",
                        message=f"Failed to load or validate JSON Schema: {e}",
                        severity="error",
                    )
                )

    # ========================================================================
    # Required Field Validation (Manual checks as supplement)
    # ========================================================================

    required_fields = ["code", "version"]
    for field in required_fields:
        if field not in manifest:
            errors.append(
                ValidationError(
                    capability=capability_code,
                    field=field,
                    message=f"Missing required field: '{field}'",
                    severity="error",
                )
            )

    # ========================================================================
    # Portability Validation
    # ========================================================================

    if "portability" not in manifest:
        errors.append(
            ValidationError(
                capability=capability_code,
                field="portability",
                message=(
                    "Missing required field: 'portability'. "
                    "Add portability declaration to support cross-environment deployment."
                ),
                severity="error",
            )
        )
    else:
        portability = manifest["portability"]

        # min_local_core_version
        if "min_local_core_version" not in portability:
            errors.append(
                ValidationError(
                    capability=capability_code,
                    field="portability.min_local_core_version",
                    message="Missing required field: 'portability.min_local_core_version'",
                    severity="error",
                )
            )

        # environments
        if "environments" not in portability:
            errors.append(
                ValidationError(
                    capability=capability_code,
                    field="portability.environments",
                    message="Missing 'portability.environments'. Must declare supported environments.",
                    severity="error",
                )
            )
        else:
            environments = portability["environments"]
            if not isinstance(environments, list):
                errors.append(
                    ValidationError(
                        capability=capability_code,
                        field="portability.environments",
                        message="'environments' must be a list",
                        severity="error",
                    )
                )
            elif "local-core" not in environments:
                capability_type = manifest.get("type", "feature")
                is_cloud_only_core = (
                    capability_type == "core"
                    and manifest.get("cloud_only", False) is True
                )

                if not is_cloud_only_core:
                    errors.append(
                        ValidationError(
                            capability=capability_code,
                            field="portability.environments",
                            message=(
                                "Capability must support 'local-core' environment "
                                "(unless type: core with cloud_only: true)."
                            ),
                            severity="error",
                        )
                    )
                else:
                    warnings.append(
                        ValidationError(
                            capability=capability_code,
                            field="portability.environments",
                            message=(
                                "cloud_only core capability: local-core not required "
                                "but verify business exemption."
                            ),
                            severity="warning",
                        )
                    )

    # ========================================================================
    # Playbook Variant Validation
    # ========================================================================

    playbooks_config = manifest.get("playbooks", [])
    for i, pb in enumerate(playbooks_config):
        if not isinstance(pb, dict):
            continue

        pb_code = pb.get("code", f"playbook_{i}")
        variants = pb.get("variants", [])
        if not isinstance(variants, list):
            continue

        seen_variant_ids = set()
        for j, variant in enumerate(variants):
            if not isinstance(variant, dict):
                continue

            vid = variant.get("variant_id")
            if not vid:
                errors.append(
                    ValidationError(
                        capability=capability_code,
                        field=f"playbooks[{pb_code}].variants[{j}]",
                        message="Variant missing required 'variant_id' field",
                        severity="error",
                    )
                )
                continue

            # Check variant_id uniqueness within this playbook
            if vid in seen_variant_ids:
                errors.append(
                    ValidationError(
                        capability=capability_code,
                        field=f"playbooks[{pb_code}].variants[{j}].variant_id",
                        message=f"Duplicate variant_id '{vid}' in playbook '{pb_code}'",
                        severity="error",
                    )
                )
            seen_variant_ids.add(vid)

            # Validate skip_steps items are integers
            skip_steps = variant.get("skip_steps", [])
            if isinstance(skip_steps, list):
                for k, step in enumerate(skip_steps):
                    if not isinstance(step, int):
                        errors.append(
                            ValidationError(
                                capability=capability_code,
                                field=f"playbooks[{pb_code}].variants[{vid}].skip_steps[{k}]",
                                message=(
                                    f"skip_steps items must be integers, "
                                    f"got {type(step).__name__}: {step}"
                                ),
                                severity="error",
                            )
                        )

    # ========================================================================
    # Tool Backend Path Validation + schema_path File Existence
    # ========================================================================

    tools = manifest.get("tools", [])
    for i, tool in enumerate(tools):
        if not isinstance(tool, dict):
            continue

        tool_name = tool.get("name", f"tool_{i}")
        backend = tool.get("backend", "")

        if backend:
            # Check if using capabilities.* format (mindscape.capabilities.* is deprecated)
            if backend.startswith("mindscape.capabilities."):
                errors.append(
                    ValidationError(
                        capability=capability_code,
                        field=f"tools[{tool_name}].backend",
                        message=(
                            f"Tool backend must use 'capabilities.*' format (mindscape.capabilities.* is deprecated), got: '{backend}'"
                        ),
                        severity="error",
                    )
                )
            elif not backend.startswith("capabilities."):
                errors.append(
                    ValidationError(
                        capability=capability_code,
                        field=f"tools[{tool_name}].backend",
                        message=(
                            f"Tool backend must start with 'capabilities.', got: '{backend}'"
                        ),
                        severity="error",
                    )
                )
            else:
                # Simple format check: capabilities.{capability}.{module}:{function}
                pattern = r"^capabilities\.[a-z0-9_]+\.[a-z0-9_.]+:[a-z0-9_]+$"
                if not re.match(pattern, backend):
                    warnings.append(
                        ValidationError(
                            capability=capability_code,
                            field=f"tools[{tool_name}].backend",
                            message=(
                                f"Tool backend format looks invalid: '{backend}'. "
                                "Expected capabilities.{capability}.{module}:{function}"
                            ),
                            severity="warning",
                        )
                    )

        # Validate schema_path file existence
        tool_schema_path = tool.get("schema_path")
        if tool_schema_path:
            schema_file, guard_error = _resolve_schema_path_guard(
                manifest_path.parent, tool_schema_path
            )
            if guard_error:
                errors.append(
                    ValidationError(
                        capability=capability_code,
                        field=f"tools[{tool_name}].schema_path",
                        message=guard_error,
                        severity="error",
                    )
                )
                continue
            if not schema_file or not schema_file.exists():
                errors.append(
                    ValidationError(
                        capability=capability_code,
                        field=f"tools[{tool_name}].schema_path",
                        message=f"Schema file not found: {tool_schema_path}",
                        severity="error",
                    )
                )

    # ========================================================================
    # API Path Validation
    # ========================================================================

    api_defs = manifest.get("apis")
    using_legacy_capabilities = False
    if api_defs is None:
        api_defs = manifest.get("capabilities", [])
        if api_defs:
            using_legacy_capabilities = True

    if using_legacy_capabilities:
        warnings.append(
            ValidationError(
                capability=capability_code,
                field="capabilities",
                message="Using deprecated field 'capabilities'. Rename to 'apis'.",
                severity="warning",
            )
        )

    for cap in api_defs or []:
        if not isinstance(cap, dict):
            continue

        cap_code = cap.get("code") or cap.get("name") or "unknown"
        path = cap.get("path", "")

        if path:
            # Check if under api/ directory
            if not path.startswith("api/"):
                errors.append(
                    ValidationError(
                        capability=capability_code,
                        field=f"apis[{cap_code}].path",
                        message="API path must be under api/ directory.",
                        severity="error",
                    )
                )

        if "prefix" not in cap or not cap.get("prefix"):
            errors.append(
                ValidationError(
                    capability=capability_code,
                    field=f"apis[{cap_code}].prefix",
                    message="Missing required field: 'prefix' (Option A rule).",
                    severity="error",
                )
            )
        else:
            prefix = cap.get("prefix")
            # Prefix should be a valid URL path (can contain multiple segments)
            # Format: /api/v1/capabilities/{capability_code} or similar
            if not isinstance(prefix, str) or not prefix.startswith("/"):
                errors.append(
                    ValidationError(
                        capability=capability_code,
                        field=f"apis[{cap_code}].prefix",
                        message=f"Invalid prefix format: '{prefix}'. Must be a string starting with '/'",
                        severity="error",
                    )
                )
            elif not re.match(r"^/[a-z0-9_/-]+$", str(prefix)):
                warnings.append(
                    ValidationError(
                        capability=capability_code,
                        field=f"apis[{cap_code}].prefix",
                        message=f"Prefix format may be invalid: '{prefix}'. Should be a valid URL path",
                        severity="warning",
                    )
                )

    # ========================================================================
    # UI Mode Validation (Phase 0.4)
    # ========================================================================

    ui_mode = manifest.get("ui_mode")
    if ui_mode is not None:
        valid_ui_modes = ["local-only", "cloud-enhanced"]
        if ui_mode not in valid_ui_modes:
            errors.append(
                ValidationError(
                    capability=capability_code,
                    field="ui_mode",
                    message=(
                        f"Invalid ui_mode: '{ui_mode}'. "
                        f"Must be one of: {', '.join(valid_ui_modes)}"
                    ),
                    severity="error",
                )
            )
        else:
            # Phase 1: Default to local-only
            if ui_mode == "cloud-enhanced":
                warnings.append(
                    ValidationError(
                        capability=capability_code,
                        field="ui_mode",
                        message=(
                            "ui_mode='cloud-enhanced' is for Phase 2. "
                            "Phase 1 should use 'local-only'."
                        ),
                        severity="warning",
                    )
                )

    cloud_compatible = manifest.get("cloud_compatible")
    if cloud_compatible is not None and not isinstance(cloud_compatible, bool):
        errors.append(
            ValidationError(
                capability=capability_code,
                field="cloud_compatible",
                message="cloud_compatible must be a boolean value.",
                severity="error",
            )
        )

    local_fallback = manifest.get("local_fallback")
    if local_fallback is not None:
        if not isinstance(local_fallback, bool):
            errors.append(
                ValidationError(
                    capability=capability_code,
                    field="local_fallback",
                    message="local_fallback must be a boolean value.",
                    severity="error",
                )
            )
        elif local_fallback and ui_mode != "cloud-enhanced":
            warnings.append(
                ValidationError(
                    capability=capability_code,
                    field="local_fallback",
                    message=(
                        "local_fallback is only relevant when ui_mode='cloud-enhanced'. "
                        "Consider removing or setting ui_mode='cloud-enhanced'."
                    ),
                    severity="warning",
                )
            )

    # ========================================================================
    # Dependencies Validation
    # ========================================================================

    dependencies = manifest.get("dependencies")

    # Guard: dependencies can be dict (standard), list (legacy), or None
    if isinstance(dependencies, dict):
        # Check if optional dependencies have fallback or degraded_features
        optional_deps = dependencies.get("optional", [])
        for dep in optional_deps:
            if isinstance(dep, dict):
                dep_name = dep.get("name") or dep.get("code") or "unknown"
                if "fallback" not in dep and "degraded_features" not in dep:
                    warnings.append(
                        ValidationError(
                            capability=capability_code,
                            field=f"dependencies.optional[{dep_name}]",
                            message=(
                                f"Optional dependency '{dep_name}' should have 'fallback' or "
                                "'degraded_features' to handle unavailability."
                            ),
                            severity="warning",
                        )
                    )
    elif isinstance(dependencies, list):
        # Legacy format: dependencies as a flat list of strings
        # Accepted but warn about migration to dict format
        if dependencies:  # non-empty list
            warnings.append(
                ValidationError(
                    capability=capability_code,
                    field="dependencies",
                    message=(
                        "dependencies is a list. Consider migrating to dict format "
                        "with 'required'/'optional' keys for richer validation."
                    ),
                    severity="warning",
                )
            )

    # ========================================================================
    # Return Results
    # ========================================================================

    return ValidationResult(
        capability=capability_code,
        valid=len(errors) == 0,
        errors=errors,
        warnings=warnings,
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
        if cap_dir.name.startswith("_") or cap_dir.name.startswith("."):
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
            lines.append(
                f"[WARN] {result.capability}: Valid with {len(result.warnings)} warning(s)"
            )
            if verbose:
                for w in result.warnings:
                    lines.append(f"   [WARN] {w.field}: {w.message}")
        else:
            lines.append(
                f"[ERROR] {result.capability}: Invalid ({len(result.errors)} error(s))"
            )
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
        "paths", nargs="+", type=Path, help="Paths to validate (capability directories)"
    )
    parser.add_argument(
        "--strict", action="store_true", help="Treat warnings as errors"
    )
    parser.add_argument(
        "--verbose", "-v", action="store_true", help="Show all warnings"
    )
    parser.add_argument("--json", action="store_true", help="Output in JSON format")

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
                        {"field": e.field, "message": e.message} for e in r.errors
                    ],
                    "warnings": [
                        {"field": w.field, "message": w.message} for w in r.warnings
                    ],
                }
                for r in all_results
            ],
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
