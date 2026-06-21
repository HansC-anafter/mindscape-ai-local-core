from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from .models import ValidationError
from .patterns import (
    CONTRACT_ID_PATTERN,
    CONTRACT_MODULE_PATTERN,
    CONTRACT_RANGE_PATTERN,
    CONTRACT_VERSION_PATTERN,
    LEGACY_ALIAS_PATTERN,
    MEETING_ARTIFACT_BACKEND_PATTERN,
    MIME_TYPE_PATTERN,
    PACK_CODE_PATTERN,
    _manifest_error,
    _manifest_warning,
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
