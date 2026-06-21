import re
from pathlib import Path
from typing import Any, Dict, List

from .aol_rules import _validate_aol_contracts
from .composition_rules import _validate_composition_graph_nodes
from .contract_rules import _resolve_schema_path_guard, _validate_contract_fields, _validate_meeting_artifact_producers
from .models import ValidationError
from .runtime_read_rules import _validate_read_model_contracts, _validate_runtime_read_path_budgets


def validate_manual_manifest_rules(
    manifest: Dict[str, Any],
    manifest_path: Path,
    capability_code: str,
    errors: List[ValidationError],
    warnings: List[ValidationError],
) -> None:
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
    _validate_composition_graph_nodes(manifest, capability_code, errors, warnings)
    _validate_runtime_read_path_budgets(manifest, capability_code, errors)
    _validate_read_model_contracts(manifest, capability_code, errors)
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
