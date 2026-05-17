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
RUNTIME_LOCK_TOKEN_PATTERN = re.compile(r"{([^{}]+)}")
RUNTIME_READ_PATH_ENDPOINT_CLASSES = {
    "ui_list",
    "summary",
    "facet",
    "sidebar",
    "status",
}
RUNTIME_READ_PATH_DB_MODELS = {
    "projection",
    "summary_table",
    "indexed_compact_query",
    "external_search_index",
}
RUNTIME_READ_PATH_REQUIRED_FIELDS = (
    "id",
    "endpoint_class",
    "method",
    "path",
    "request_query",
    "purpose",
    "max_ttfb_ms",
    "max_total_ms",
    "max_response_bytes",
    "db_read_model",
    "forbidden_sources",
    "expected_status",
)
RUNTIME_READ_PATH_DENY_LIST_REQUIRED_CLASSES = {
    "ui_list",
    "summary",
    "facet",
    "sidebar",
}


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


def _validate_pack_backend(
    *,
    capability_code: str,
    field: str,
    backend: object,
    errors: List[ValidationError],
    warnings: List[ValidationError],
) -> None:
    if not isinstance(backend, str) or not AOL_BACKEND_PATTERN.match(backend):
        errors.append(
            _manifest_error(
                capability_code,
                field,
                "backend must be a pack-owned backend import path",
            )
        )
        return
    module_path, _symbol = backend.split(":", 1)
    if capability_code and not (
        module_path.startswith(f"capabilities.{capability_code}.")
        or module_path.startswith(f"app.capabilities.{capability_code}.")
    ):
        warnings.append(
            _manifest_warning(
                capability_code,
                field,
                f"backend does not appear to be owned by pack '{capability_code}'",
            )
        )


def _validate_composition_graph_nodes(
    manifest: Dict[str, Any],
    capability_code: str,
    errors: List[ValidationError],
    warnings: List[ValidationError],
) -> None:
    contract = manifest.get("composition_graph_nodes")
    if contract is None:
        return
    if not isinstance(contract, dict):
        errors.append(
            _manifest_error(
                capability_code,
                "composition_graph_nodes",
                "composition_graph_nodes must be an object",
            )
        )
        return
    if contract.get("enabled") is not True:
        return
    nodes = contract.get("nodes")
    if not isinstance(nodes, list):
        errors.append(
            _manifest_error(
                capability_code,
                "composition_graph_nodes.nodes",
                "composition_graph_nodes.nodes must be a list",
            )
        )
        return
    for index, node in enumerate(nodes):
        field_prefix = f"composition_graph_nodes.nodes[{index}]"
        if not isinstance(node, dict):
            errors.append(
                _manifest_error(
                    capability_code,
                    field_prefix,
                    "node must be an object",
                )
            )
            continue
        if node.get("id") == "object_reference":
            errors.append(
                _manifest_error(
                    capability_code,
                    f"{field_prefix}.id",
                    "pack node id cannot be object_reference",
                )
            )
        _validate_composition_graph_node_ports(
            capability_code,
            field_prefix,
            node.get("input_ports"),
            "input",
            errors,
        )
        _validate_composition_graph_node_ports(
            capability_code,
            field_prefix,
            node.get("output_ports"),
            "output",
            errors,
        )
        payload_schema = node.get("payload_schema", {})
        if payload_schema is not None and not isinstance(payload_schema, dict):
            errors.append(
                _manifest_error(
                    capability_code,
                    f"{field_prefix}.payload_schema",
                    "payload_schema must be an object",
                )
            )
        executor = node.get("executor")
        if not isinstance(executor, dict):
            errors.append(
                _manifest_error(
                    capability_code,
                    f"{field_prefix}.executor",
                    "executor must be an object",
                )
            )
        else:
            _validate_pack_backend(
                capability_code=capability_code,
                field=f"{field_prefix}.executor.backend",
                backend=executor.get("backend"),
                errors=errors,
                warnings=warnings,
            )
        option_sources = node.get("option_sources", {})
        if option_sources is not None:
            if not isinstance(option_sources, dict):
                errors.append(
                    _manifest_error(
                        capability_code,
                        f"{field_prefix}.option_sources",
                        "option_sources must be an object",
                    )
                )
            else:
                for option_field, option_source in option_sources.items():
                    option_prefix = f"{field_prefix}.option_sources.{option_field}"
                    if not isinstance(option_source, dict):
                        errors.append(
                            _manifest_error(
                                capability_code,
                                option_prefix,
                                "option source must be an object",
                            )
                        )
                        continue
                    _validate_pack_backend(
                        capability_code=capability_code,
                        field=f"{option_prefix}.backend",
                        backend=option_source.get("backend"),
                        errors=errors,
                        warnings=warnings,
                    )
        runtime_lock = node.get("runtime_lock")
        if runtime_lock is not None:
            if not isinstance(runtime_lock, dict):
                errors.append(
                    _manifest_error(
                        capability_code,
                        f"{field_prefix}.runtime_lock",
                        "runtime_lock must be an object",
                    )
                )
            else:
                if runtime_lock.get("max_parallel") != 1:
                    errors.append(
                        _manifest_error(
                            capability_code,
                            f"{field_prefix}.runtime_lock.max_parallel",
                            "runtime_lock.max_parallel must be 1",
                        )
                    )
                key_template = runtime_lock.get("key_template")
                if not isinstance(key_template, str) or not key_template.strip():
                    errors.append(
                        _manifest_error(
                            capability_code,
                            f"{field_prefix}.runtime_lock.key_template",
                            "runtime_lock.key_template must be a non-empty string",
                        )
                    )
                else:
                    _validate_runtime_lock_template(
                        capability_code,
                        f"{field_prefix}.runtime_lock.key_template",
                        key_template,
                        errors,
                    )


def _validate_composition_graph_node_ports(
    capability_code: str,
    field_prefix: str,
    ports: object,
    direction: str,
    errors: List[ValidationError],
) -> None:
    if not isinstance(ports, list):
        errors.append(
            _manifest_error(
                capability_code,
                f"{field_prefix}.{direction}_ports",
                f"{direction}_ports must be a list",
            )
        )
        return
    for port_index, port in enumerate(ports):
        port_prefix = f"{field_prefix}.{direction}_ports[{port_index}]"
        if not isinstance(port, dict):
            errors.append(
                _manifest_error(
                    capability_code,
                    port_prefix,
                    "port must be an object",
                )
            )
            continue
        if port.get("direction") != direction:
            errors.append(
                _manifest_error(
                    capability_code,
                    f"{port_prefix}.direction",
                    f"port direction must be {direction}",
                )
            )


def _validate_runtime_lock_template(
    capability_code: str,
    field: str,
    key_template: str,
    errors: List[ValidationError],
) -> None:
    for match in RUNTIME_LOCK_TOKEN_PATTERN.finditer(key_template):
        token = match.group(1)
        if token == "workspace_id":
            continue
        if token.startswith("payload.") and token.removeprefix("payload."):
            continue
        errors.append(
            _manifest_error(
                capability_code,
                field,
                "runtime_lock.key_template only supports {workspace_id} and {payload.<field>} tokens",
            )
        )


def _declared_api_prefixes(manifest: Dict[str, Any]) -> List[str]:
    prefixes = []
    api_defs = manifest.get("apis") or manifest.get("capabilities") or []
    if not isinstance(api_defs, list):
        return prefixes
    for api_def in api_defs:
        if not isinstance(api_def, dict):
            continue
        prefix = api_def.get("prefix")
        if isinstance(prefix, str) and prefix.startswith("/"):
            prefixes.append(prefix.rstrip("/") or "/")
    return prefixes


def _path_under_api_prefix(path: str, prefixes: List[str]) -> bool:
    normalized_path = path.rstrip("/") or "/"
    for prefix in prefixes:
        normalized_prefix = prefix.rstrip("/") or "/"
        if normalized_path == normalized_prefix:
            return True
        if normalized_path.startswith(f"{normalized_prefix}/"):
            return True
    return False


def _validate_runtime_read_path_budgets(
    manifest: Dict[str, Any],
    capability_code: str,
    errors: List[ValidationError],
) -> None:
    budgets = manifest.get("runtime_read_path_budgets")
    if budgets is None:
        return
    if not isinstance(budgets, list):
        errors.append(
            _manifest_error(
                capability_code,
                "runtime_read_path_budgets",
                "runtime_read_path_budgets must be a list",
            )
        )
        return
    if not budgets:
        errors.append(
            _manifest_error(
                capability_code,
                "runtime_read_path_budgets",
                "runtime_read_path_budgets must declare at least one budget",
            )
        )
        return

    api_prefixes = _declared_api_prefixes(manifest)
    seen_ids = set()
    for index, budget in enumerate(budgets):
        field_prefix = f"runtime_read_path_budgets[{index}]"
        if not isinstance(budget, dict):
            errors.append(
                _manifest_error(
                    capability_code,
                    field_prefix,
                    "budget item must be an object",
                )
            )
            continue

        for required_field in RUNTIME_READ_PATH_REQUIRED_FIELDS:
            if required_field not in budget:
                errors.append(
                    _manifest_error(
                        capability_code,
                        f"{field_prefix}.{required_field}",
                        f"Missing required budget field: {required_field}",
                    )
                )

        budget_id = budget.get("id")
        if not isinstance(budget_id, str) or not CONTRACT_ID_PATTERN.match(budget_id):
            errors.append(
                _manifest_error(
                    capability_code,
                    f"{field_prefix}.id",
                    "id must match ^[a-z0-9_]+$",
                )
            )
        elif budget_id in seen_ids:
            errors.append(
                _manifest_error(
                    capability_code,
                    f"{field_prefix}.id",
                    "id must be unique",
                )
            )
        else:
            seen_ids.add(budget_id)

        endpoint_class = budget.get("endpoint_class")
        if endpoint_class not in RUNTIME_READ_PATH_ENDPOINT_CLASSES:
            errors.append(
                _manifest_error(
                    capability_code,
                    f"{field_prefix}.endpoint_class",
                    (
                        "endpoint_class must be one of: "
                        f"{', '.join(sorted(RUNTIME_READ_PATH_ENDPOINT_CLASSES))}"
                    ),
                )
            )

        method = budget.get("method")
        if method != "GET":
            errors.append(
                _manifest_error(
                    capability_code,
                    f"{field_prefix}.method",
                    "method must be GET",
                )
            )

        path = budget.get("path")
        if not isinstance(path, str) or not path.startswith("/"):
            errors.append(
                _manifest_error(
                    capability_code,
                    f"{field_prefix}.path",
                    "path must be a fully mounted absolute path",
                )
            )
        elif not api_prefixes:
            errors.append(
                _manifest_error(
                    capability_code,
                    f"{field_prefix}.path",
                    "path cannot be checked because manifest has no API prefixes",
                )
            )
        elif not _path_under_api_prefix(path, api_prefixes):
            errors.append(
                _manifest_error(
                    capability_code,
                    f"{field_prefix}.path",
                    "path must be under a declared API prefix",
                )
            )

        request_query = budget.get("request_query")
        if not isinstance(request_query, dict) or not request_query:
            errors.append(
                _manifest_error(
                    capability_code,
                    f"{field_prefix}.request_query",
                    "request_query must be a non-empty object",
                )
            )
        else:
            for query_key, query_value in request_query.items():
                if not isinstance(query_key, str) or not query_key.strip():
                    errors.append(
                        _manifest_error(
                            capability_code,
                            f"{field_prefix}.request_query",
                            "request_query keys must be non-empty strings",
                        )
                    )
                    continue
                if query_value is None or isinstance(query_value, (list, dict)):
                    errors.append(
                        _manifest_error(
                            capability_code,
                            f"{field_prefix}.request_query.{query_key}",
                            "request_query values must be scalar",
                        )
                    )
            if endpoint_class != "status" and "workspace_id" not in request_query:
                errors.append(
                    _manifest_error(
                        capability_code,
                        f"{field_prefix}.request_query",
                        "request_query must include workspace_id for governed read endpoints",
                    )
                )

        purpose = budget.get("purpose")
        if not isinstance(purpose, str) or not purpose.strip():
            errors.append(
                _manifest_error(
                    capability_code,
                    f"{field_prefix}.purpose",
                    "purpose must be a non-empty string",
                )
            )

        for budget_field in ("max_ttfb_ms", "max_total_ms", "max_response_bytes"):
            value = budget.get(budget_field)
            if type(value) is not int or value <= 0:
                errors.append(
                    _manifest_error(
                        capability_code,
                        f"{field_prefix}.{budget_field}",
                        f"{budget_field} must be a positive integer",
                    )
                )

        db_read_model = budget.get("db_read_model")
        if db_read_model not in RUNTIME_READ_PATH_DB_MODELS:
            errors.append(
                _manifest_error(
                    capability_code,
                    f"{field_prefix}.db_read_model",
                    (
                        "db_read_model must be one of: "
                        f"{', '.join(sorted(RUNTIME_READ_PATH_DB_MODELS))}"
                    ),
                )
            )

        forbidden_sources = budget.get("forbidden_sources")
        read_model_id = budget.get("read_model_id")
        if read_model_id is not None:
            invalid_forbidden_sources = (
                not isinstance(forbidden_sources, list)
                or not forbidden_sources
                or any(
                    not isinstance(source, dict)
                    or not isinstance(source.get("relation"), str)
                    or not source.get("relation").strip()
                    or not isinstance(source.get("columns"), list)
                    or not source.get("columns")
                    or any(
                        not isinstance(column, str) or not column.strip()
                        for column in source.get("columns", [])
                    )
                    for source in forbidden_sources or []
                )
            )
        else:
            invalid_forbidden_sources = not isinstance(forbidden_sources, list) or any(
                not isinstance(source, str) or not source.strip()
                for source in forbidden_sources or []
            )
        if invalid_forbidden_sources:
            source_message = (
                "forbidden_sources must be a list of {relation, columns} objects"
                if read_model_id is not None
                else "forbidden_sources must be a list of non-empty strings"
            )
            errors.append(
                _manifest_error(
                    capability_code,
                    f"{field_prefix}.forbidden_sources",
                    source_message,
                )
            )
        elif (
            endpoint_class in RUNTIME_READ_PATH_DENY_LIST_REQUIRED_CLASSES
            and not forbidden_sources
        ):
            errors.append(
                _manifest_error(
                    capability_code,
                    f"{field_prefix}.forbidden_sources",
                    "forbidden_sources must declare at least one denied source",
                )
            )

        expected_status = budget.get("expected_status")
        if type(expected_status) is not int or not 100 <= expected_status <= 599:
            errors.append(
                _manifest_error(
                    capability_code,
                    f"{field_prefix}.expected_status",
                    "expected_status must be an HTTP status integer",
                )
            )


def _as_list(value: Any) -> List[Any]:
    return value if isinstance(value, list) else []


def _validate_read_model_contracts(
    manifest: Dict[str, Any],
    capability_code: str,
    errors: List[ValidationError],
) -> None:
    read_models = manifest.get("read_models")
    count_models = manifest.get("count_models")
    if read_models is None and count_models is None:
        return

    if read_models is not None and not isinstance(read_models, list):
        errors.append(
            _manifest_error(
                capability_code,
                "read_models",
                "read_models must be a list",
            )
        )
        read_models = []
    if count_models is not None and not isinstance(count_models, list):
        errors.append(
            _manifest_error(
                capability_code,
                "count_models",
                "count_models must be a list",
            )
        )
        count_models = []

    read_model_ids: set[str] = set()
    for index, read_model in enumerate(read_models or []):
        prefix = f"read_models[{index}]"
        if not isinstance(read_model, dict):
            errors.append(_manifest_error(capability_code, prefix, "read model must be an object"))
            continue
        read_model_id = read_model.get("id")
        if not isinstance(read_model_id, str) or not CONTRACT_ID_PATTERN.match(read_model_id):
            errors.append(
                _manifest_error(
                    capability_code,
                    f"{prefix}.id",
                    "id must match ^[a-z0-9_]+$",
                )
            )
        elif read_model_id in read_model_ids:
            errors.append(_manifest_error(capability_code, f"{prefix}.id", "id must be unique"))
        else:
            read_model_ids.add(read_model_id)

        if read_model.get("owner_pack") != capability_code:
            errors.append(
                _manifest_error(
                    capability_code,
                    f"{prefix}.owner_pack",
                    "owner_pack must equal manifest code",
                )
            )
        contract_version = read_model.get("contract_version")
        if type(contract_version) is not int or contract_version <= 0:
            errors.append(
                _manifest_error(
                    capability_code,
                    f"{prefix}.contract_version",
                    "contract_version must be a positive integer",
                )
            )
        if not isinstance(read_model.get("table"), str) or not AOL_FIELD_PATTERN.match(read_model.get("table", "")):
            errors.append(
                _manifest_error(
                    capability_code,
                    f"{prefix}.table",
                    "table must be a SQL identifier",
                )
            )

        field_ids = {
            field.get("id")
            for field in _as_list(read_model.get("fields"))
            if isinstance(field, dict) and isinstance(field.get("id"), str)
        }
        if not field_ids:
            errors.append(_manifest_error(capability_code, f"{prefix}.fields", "fields must be non-empty"))
        for field_index, field in enumerate(_as_list(read_model.get("fields"))):
            field_prefix = f"{prefix}.fields[{field_index}]"
            if not isinstance(field, dict):
                errors.append(_manifest_error(capability_code, field_prefix, "field must be an object"))
                continue
            if not isinstance(field.get("id"), str) or not CONTRACT_ID_PATTERN.match(field.get("id", "")):
                errors.append(_manifest_error(capability_code, f"{field_prefix}.id", "id must match ^[a-z0-9_]+$"))
            if not isinstance(field.get("column"), str) or not AOL_FIELD_PATTERN.match(field.get("column", "")):
                errors.append(_manifest_error(capability_code, f"{field_prefix}.column", "column must be a SQL identifier"))
            if not isinstance(field.get("type"), str) or not field.get("type"):
                errors.append(_manifest_error(capability_code, f"{field_prefix}.type", "type must be a non-empty string"))

        for filter_index, filter_item in enumerate(_as_list(read_model.get("filters"))):
            filter_prefix = f"{prefix}.filters[{filter_index}]"
            if not isinstance(filter_item, dict):
                errors.append(_manifest_error(capability_code, filter_prefix, "filter must be an object"))
                continue
            if filter_item.get("field") not in field_ids:
                errors.append(_manifest_error(capability_code, f"{filter_prefix}.field", "field must reference read_models[].fields[].id"))

        stable_key = read_model.get("stable_key")
        if not isinstance(stable_key, list) or not stable_key or any(key not in field_ids for key in stable_key):
            errors.append(_manifest_error(capability_code, f"{prefix}.stable_key", "stable_key must reference declared fields"))

        sort_ids: set[str] = set()
        for sort_index, sort_item in enumerate(_as_list(read_model.get("sorts"))):
            sort_prefix = f"{prefix}.sorts[{sort_index}]"
            if not isinstance(sort_item, dict):
                errors.append(_manifest_error(capability_code, sort_prefix, "sort must be an object"))
                continue
            sort_id = sort_item.get("id")
            if isinstance(sort_id, str) and CONTRACT_ID_PATTERN.match(sort_id):
                sort_ids.add(sort_id)
            fields = _as_list(sort_item.get("fields"))
            sort_fields = [field.get("field") for field in fields if isinstance(field, dict)]
            if not fields or any(field_name not in field_ids for field_name in sort_fields):
                errors.append(_manifest_error(capability_code, f"{sort_prefix}.fields", "sort fields must reference declared fields"))
            if isinstance(stable_key, list) and stable_key and not set(stable_key).issubset(set(sort_fields)):
                errors.append(_manifest_error(capability_code, sort_prefix, "sort must include stable_key fields as tiebreakers"))
        if not sort_ids:
            errors.append(_manifest_error(capability_code, f"{prefix}.sorts", "sorts must declare at least one sort"))

        covered_sorts = {
            sort_id
            for index_item in _as_list(read_model.get("indexes"))
            if isinstance(index_item, dict)
            for sort_id in _as_list(index_item.get("covers_sort"))
        }
        missing_sorts = sort_ids - covered_sorts
        if missing_sorts:
            errors.append(_manifest_error(capability_code, f"{prefix}.indexes", f"indexes must cover declared sorts: {sorted(missing_sorts)}"))

        cursor = read_model.get("cursor")
        if (
            not isinstance(cursor, dict)
            or cursor.get("strategy") != "keyset"
            or cursor.get("signed") is not True
            or type(cursor.get("ttl_seconds")) is not int
            or cursor.get("ttl_seconds") <= 0
        ):
            errors.append(_manifest_error(capability_code, f"{prefix}.cursor", "cursor must declare signed keyset with ttl_seconds"))

    count_models_by_id: Dict[str, Dict[str, Any]] = {}
    for index, count_model in enumerate(count_models or []):
        prefix = f"count_models[{index}]"
        if not isinstance(count_model, dict):
            errors.append(_manifest_error(capability_code, prefix, "count model must be an object"))
            continue
        count_model_id = count_model.get("id")
        if not isinstance(count_model_id, str) or not CONTRACT_ID_PATTERN.match(count_model_id):
            errors.append(_manifest_error(capability_code, f"{prefix}.id", "id must match ^[a-z0-9_]+$"))
            continue
        if count_model_id in count_models_by_id:
            errors.append(_manifest_error(capability_code, f"{prefix}.id", "id must be unique"))
        count_models_by_id[count_model_id] = count_model
        if count_model.get("read_model_id") not in read_model_ids:
            errors.append(_manifest_error(capability_code, f"{prefix}.read_model_id", "read_model_id must reference read_models[].id"))
        for field_name in ("table", "key_columns", "supported_filter_sets", "measures"):
            if field_name not in count_model:
                errors.append(_manifest_error(capability_code, f"{prefix}.{field_name}", f"{field_name} is required"))

    for index, budget in enumerate(_as_list(manifest.get("runtime_read_path_budgets"))):
        if not isinstance(budget, dict):
            continue
        prefix = f"runtime_read_path_budgets[{index}]"
        read_model_id = budget.get("read_model_id")
        count_model_id = budget.get("count_model_id")
        if read_model_id is not None:
            if read_model_id not in read_model_ids:
                errors.append(_manifest_error(capability_code, f"{prefix}.read_model_id", "read_model_id must reference read_models[].id"))
            if budget.get("endpoint_class") == "ui_list" and budget.get("db_read_model") == "projection":
                if count_model_id not in count_models_by_id:
                    errors.append(_manifest_error(capability_code, f"{prefix}.count_model_id", "count_model_id must reference count_models[].id"))
                elif count_models_by_id[count_model_id].get("read_model_id") != read_model_id:
                    errors.append(_manifest_error(capability_code, f"{prefix}.count_model_id", "count_model_id must reference a count model for the same read_model_id"))
        elif count_model_id is not None:
            errors.append(_manifest_error(capability_code, f"{prefix}.count_model_id", "count_model_id requires read_model_id"))


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
