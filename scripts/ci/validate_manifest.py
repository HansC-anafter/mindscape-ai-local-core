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


AOL_LEVELS = {
    "AOL-0": 0,
    "AOL-1": 1,
    "AOL-2": 2,
    "AOL-3": 3,
    "AOL-4": 4,
    "AOL-5": 5,
}
AOL_SELECTOR_FAMILIES = {
    "object_root",
    "dom_anchor",
    "image_region",
    "media_time_range",
    "storyboard_scene",
    "storyboard_slot",
    "timeline_clip",
    "pack_local_path",
    "graph_node",
}
AOL_ROLES = {
    "source",
    "target",
    "character",
    "constraint",
    "output",
    "meeting",
    "session",
    "node",
}
AOL_WRITE_MODES = {
    "proposal_only",
    "staged",
    "canonical_with_review",
    "owner_canonical_lane",
    "recommendation_only",
}
AOL_BACKEND_PATTERN = re.compile(
    r"^(app\.)?capabilities\.[a-z0-9_]+(?:\.[A-Za-z0-9_]+)+:[A-Za-z_][A-Za-z0-9_]*$"
)
AOL_OBJECT_KIND_PATTERN = re.compile(r"^[a-z0-9_]+$")
AOL_FIELD_PATTERN = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
PACK_CODE_PATTERN = re.compile(r"^[a-z0-9_]+$")
CONTRACT_ID_PATTERN = re.compile(r"^[a-z0-9_]+$")
CONTRACT_MODULE_PATTERN = re.compile(
    r"^(app\.)?capabilities\.[a-z0-9_]+\.schema(?:\.[A-Za-z0-9_]+)+$"
)
CONTRACT_VERSION_PATTERN = re.compile(
    r"^[0-9]+\.[0-9]+(?:\.[0-9]+)?(?:[-+][A-Za-z0-9_.-]+)?$"
)
CONTRACT_RANGE_PATTERN = re.compile(r"^[\^~<>=!, 0-9A-Za-z_.-]+$")
LEGACY_ALIAS_PATTERN = re.compile(
    r"^(shared|backend\.shared)\.schemas\.[A-Za-z0-9_]+$"
)
MIME_TYPE_PATTERN = re.compile(
    r"^[A-Za-z0-9!#$&^_.+-]+/[A-Za-z0-9!#$&^_.+-]+(?:\+[A-Za-z0-9!#$&^_.+-]+)?$"
)
MEETING_ARTIFACT_BACKEND_PATTERN = re.compile(
    r"^capabilities\.[a-z0-9_]+\.[A-Za-z0-9_\.]+:[A-Za-z_][A-Za-z0-9_]*$"
)


def _aol_error(
    capability_code: str,
    field: str,
    message: str,
) -> ValidationError:
    return ValidationError(
        capability=capability_code,
        field=field,
        message=message,
        severity="error",
    )


def _validate_aol_contracts(
    manifest: Dict[str, Any],
    capability_code: str,
    errors: List[ValidationError],
    warnings: List[ValidationError],
) -> None:
    maturity = manifest.get("aol_maturity")
    maturity_level = 0
    if maturity is not None:
        if not isinstance(maturity, str) or maturity not in AOL_LEVELS:
            errors.append(
                _aol_error(
                    capability_code,
                    "aol_maturity",
                    "aol_maturity must be one of AOL-0 through AOL-5",
                )
            )
        else:
            maturity_level = AOL_LEVELS[maturity]

    object_exports = manifest.get("object_exports") or []
    declared_kinds = set()
    if object_exports and not isinstance(object_exports, list):
        errors.append(
            _aol_error(capability_code, "object_exports", "object_exports must be a list")
        )
        object_exports = []

    for index, export in enumerate(object_exports):
        field_prefix = f"object_exports[{index}]"
        if not isinstance(export, dict):
            errors.append(
                _aol_error(capability_code, field_prefix, "object export must be an object")
            )
            continue

        kind = export.get("kind")
        if isinstance(kind, str) and AOL_OBJECT_KIND_PATTERN.match(kind):
            declared_kinds.add(kind)

        selector_families = export.get("selector_families")
        if selector_families is not None:
            if not isinstance(selector_families, list) or any(
                family not in AOL_SELECTOR_FAMILIES for family in selector_families
            ):
                errors.append(
                    _aol_error(
                        capability_code,
                        f"{field_prefix}.selector_families",
                        "selector_families must use known AOL selector family names",
                    )
                )
        elif maturity_level >= 2:
            errors.append(
                _aol_error(
                    capability_code,
                    f"{field_prefix}.selector_families",
                    "AOL-2+ object exports must declare selector_families",
                )
            )

        indexer_backend = export.get("indexer_backend")
        if indexer_backend is not None:
            if not isinstance(indexer_backend, str) or not AOL_BACKEND_PATTERN.match(
                indexer_backend
            ):
                errors.append(
                    _aol_error(
                        capability_code,
                        f"{field_prefix}.indexer_backend",
                        "indexer_backend must be a pack-owned backend import path",
                    )
                )
        elif maturity_level >= 2:
            errors.append(
                _aol_error(
                    capability_code,
                    f"{field_prefix}.indexer_backend",
                    "AOL-2+ object exports must declare indexer_backend",
                )
            )

        mention_fields = export.get("mention_fields")
        if mention_fields is not None:
            if not isinstance(mention_fields, list) or any(
                not isinstance(field_name, str) or not AOL_FIELD_PATTERN.match(field_name)
                for field_name in mention_fields
            ):
                errors.append(
                    _aol_error(
                        capability_code,
                        f"{field_prefix}.mention_fields",
                        "mention_fields must be a list of field identifiers",
                    )
                )
        elif maturity_level >= 2:
            errors.append(
                _aol_error(
                    capability_code,
                    f"{field_prefix}.mention_fields",
                    "AOL-2+ object exports must declare mention_fields",
                )
            )

    affordances = manifest.get("affordances") or []
    if affordances and not isinstance(affordances, list):
        errors.append(_aol_error(capability_code, "affordances", "affordances must be a list"))
        affordances = []
    if maturity_level >= 2 and not affordances:
        errors.append(
            _aol_error(
                capability_code,
                "affordances",
                "AOL-2+ packs must declare at least one schema-backed affordance",
            )
        )

    for index, affordance in enumerate(affordances):
        field_prefix = f"affordances[{index}]"
        if not isinstance(affordance, dict):
            errors.append(
                _aol_error(capability_code, field_prefix, "affordance must be an object")
            )
            continue

        for required_field in (
            "verb",
            "input_schema",
            "output_schema",
            "required_roles",
            "write_modes",
            "planner_backend",
        ):
            if required_field not in affordance:
                errors.append(
                    _aol_error(
                        capability_code,
                        f"{field_prefix}.{required_field}",
                        f"Missing required affordance field: {required_field}",
                    )
                )

        object_kinds = affordance.get("object_kinds") or []
        if object_kinds and (
            not isinstance(object_kinds, list)
            or any(kind not in declared_kinds for kind in object_kinds)
        ):
            errors.append(
                _aol_error(
                    capability_code,
                    f"{field_prefix}.object_kinds",
                    "object_kinds must reference declared object_exports kinds",
                )
            )

        required_roles = affordance.get("required_roles")
        if required_roles is not None and (
            not isinstance(required_roles, list)
            or not required_roles
            or any(role not in AOL_ROLES for role in required_roles)
        ):
            errors.append(
                _aol_error(
                    capability_code,
                    f"{field_prefix}.required_roles",
                    "required_roles must be a non-empty list of known AOL roles",
                )
            )

        write_modes = affordance.get("write_modes")
        if write_modes is not None and (
            not isinstance(write_modes, list)
            or not write_modes
            or any(mode not in AOL_WRITE_MODES for mode in write_modes)
        ):
            errors.append(
                _aol_error(
                    capability_code,
                    f"{field_prefix}.write_modes",
                    "write_modes must be a non-empty list of supported write modes",
                )
            )

        for backend_field in ("planner_backend", "executor_backend"):
            backend = affordance.get(backend_field)
            if backend is not None and (
                not isinstance(backend, str) or not AOL_BACKEND_PATTERN.match(backend)
            ):
                errors.append(
                    _aol_error(
                        capability_code,
                        f"{field_prefix}.{backend_field}",
                        f"{backend_field} must be a pack-owned backend import path",
                    )
                )


def _manifest_error(
    capability_code: str,
    field: str,
    message: str,
) -> ValidationError:
    return ValidationError(
        capability=capability_code,
        field=field,
        message=message,
        severity="error",
    )


def _manifest_warning(
    capability_code: str,
    field: str,
    message: str,
) -> ValidationError:
    return ValidationError(
        capability=capability_code,
        field=field,
        message=message,
        severity="warning",
    )


def _validate_contract_fields(
    manifest: Dict[str, Any],
    capability_code: str,
    errors: List[ValidationError],
    warnings: List[ValidationError],
) -> None:
    contract_exports = manifest.get("contract_exports")
    if contract_exports is not None:
        if not isinstance(contract_exports, list):
            errors.append(
                _manifest_error(
                    capability_code,
                    "contract_exports",
                    "contract_exports must be a list",
                )
            )
        else:
            for index, export in enumerate(contract_exports):
                field_prefix = f"contract_exports[{index}]"
                if not isinstance(export, dict):
                    errors.append(
                        _manifest_error(
                            capability_code,
                            field_prefix,
                            "contract export must be an object",
                        )
                    )
                    continue
                contract_id = export.get("contract_id", "")
                module = export.get("module", "")
                version = export.get("version", "")
                if not isinstance(contract_id, str) or not CONTRACT_ID_PATTERN.match(
                    contract_id
                ):
                    errors.append(
                        _manifest_error(
                            capability_code,
                            f"{field_prefix}.contract_id",
                            "contract_id must match ^[a-z0-9_]+$",
                        )
                    )
                if not isinstance(module, str) or not CONTRACT_MODULE_PATTERN.match(
                    module
                ):
                    errors.append(
                        _manifest_error(
                            capability_code,
                            f"{field_prefix}.module",
                            "module must point to a pack-owned schema module",
                        )
                    )
                elif capability_code and not (
                    module.startswith(f"capabilities.{capability_code}.")
                    or module.startswith(f"app.capabilities.{capability_code}.")
                ):
                    warnings.append(
                        _manifest_warning(
                            capability_code,
                            f"{field_prefix}.module",
                            (
                                "module does not appear to be owned by pack "
                                f"'{capability_code}'"
                            ),
                        )
                    )
                if not isinstance(version, str) or not CONTRACT_VERSION_PATTERN.match(
                    version
                ):
                    errors.append(
                        _manifest_error(
                            capability_code,
                            f"{field_prefix}.version",
                            "version must be a semver-like string",
                        )
                    )
                legacy_aliases = export.get("legacy_aliases", [])
                if legacy_aliases is None:
                    legacy_aliases = []
                if not isinstance(legacy_aliases, list) or any(
                    not isinstance(alias, str) or not LEGACY_ALIAS_PATTERN.match(alias)
                    for alias in legacy_aliases
                ):
                    errors.append(
                        _manifest_error(
                            capability_code,
                            f"{field_prefix}.legacy_aliases",
                            (
                                "legacy_aliases must be shared.schemas.* or "
                                "backend.shared.schemas.* strings"
                            ),
                        )
                    )

    contract_imports = manifest.get("contract_imports")
    if contract_imports is not None:
        if not isinstance(contract_imports, list):
            errors.append(
                _manifest_error(
                    capability_code,
                    "contract_imports",
                    "contract_imports must be a list",
                )
            )
        else:
            for index, contract_import in enumerate(contract_imports):
                field_prefix = f"contract_imports[{index}]"
                if not isinstance(contract_import, dict):
                    errors.append(
                        _manifest_error(
                            capability_code,
                            field_prefix,
                            "contract import must be an object",
                        )
                    )
                    continue
                contract_id = contract_import.get("contract_id", "")
                provider_pack = contract_import.get("provider_pack", "")
                version_range = contract_import.get("version_range", "")
                if not isinstance(contract_id, str) or not CONTRACT_ID_PATTERN.match(
                    contract_id
                ):
                    errors.append(
                        _manifest_error(
                            capability_code,
                            f"{field_prefix}.contract_id",
                            "contract_id must match ^[a-z0-9_]+$",
                        )
                    )
                if not isinstance(provider_pack, str) or not PACK_CODE_PATTERN.match(
                    provider_pack
                ):
                    errors.append(
                        _manifest_error(
                            capability_code,
                            f"{field_prefix}.provider_pack",
                            "provider_pack must be a lowercase pack code",
                        )
                    )
                if not isinstance(version_range, str) or not CONTRACT_RANGE_PATTERN.match(
                    version_range
                ):
                    errors.append(
                        _manifest_error(
                            capability_code,
                            f"{field_prefix}.version_range",
                            "version_range must be a non-empty semver range string",
                        )
                    )


def _validate_meeting_artifact_producers(
    manifest: Dict[str, Any],
    capability_code: str,
    errors: List[ValidationError],
) -> None:
    producers = manifest.get("meeting_artifact_producers")
    if producers is None:
        return
    if not isinstance(producers, list):
        errors.append(
            _manifest_error(
                capability_code,
                "meeting_artifact_producers",
                "meeting_artifact_producers must be a list",
            )
        )
        return

    for index, producer in enumerate(producers):
        field_prefix = f"meeting_artifact_producers[{index}]"
        if not isinstance(producer, dict):
            errors.append(
                _manifest_error(
                    capability_code,
                    field_prefix,
                    "meeting artifact producer must be an object",
                )
            )
            continue

        mime_type = producer.get("mime_type", "")
        backend = producer.get("backend", "")
        governance_request_key = producer.get("governance_request_key")
        input_contract = producer.get("input_contract", "")

        if not isinstance(mime_type, str) or not MIME_TYPE_PATTERN.match(mime_type):
            errors.append(
                _manifest_error(
                    capability_code,
                    f"{field_prefix}.mime_type",
                    "mime_type must be a valid MIME type",
                )
            )
        if not isinstance(backend, str) or not MEETING_ARTIFACT_BACKEND_PATTERN.match(
            backend
        ):
            errors.append(
                _manifest_error(
                    capability_code,
                    f"{field_prefix}.backend",
                    "backend must use capabilities.<pack>.<module>:<callable>",
                )
            )
        elif capability_code and not backend.startswith(f"capabilities.{capability_code}."):
            errors.append(
                _manifest_error(
                    capability_code,
                    f"{field_prefix}.backend",
                    "backend must be owned by the declaring capability pack",
                )
            )
        if governance_request_key is not None and (
            not isinstance(governance_request_key, str)
            or not PACK_CODE_PATTERN.match(governance_request_key)
        ):
            errors.append(
                _manifest_error(
                    capability_code,
                    f"{field_prefix}.governance_request_key",
                    "governance_request_key must match ^[a-z0-9_]+$",
                )
            )
        if not isinstance(input_contract, str) or not CONTRACT_ID_PATTERN.match(
            input_contract
        ):
            errors.append(
                _manifest_error(
                    capability_code,
                    f"{field_prefix}.input_contract",
                    "input_contract must match ^[a-z0-9_]+$",
                )
            )


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

    _validate_aol_contracts(manifest, capability_code, errors, warnings)
    _validate_contract_fields(manifest, capability_code, errors, warnings)
    _validate_meeting_artifact_producers(manifest, capability_code, errors)

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
