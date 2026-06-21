from typing import Any, Dict, List

from .models import ValidationError
from .patterns import (
    AOL_BACKEND_PATTERN,
    AOL_FIELD_PATTERN,
    AOL_LEVELS,
    AOL_OBJECT_KIND_PATTERN,
    AOL_ROLES,
    AOL_SELECTOR_FAMILIES,
    AOL_WRITE_MODES,
    _aol_error,
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
