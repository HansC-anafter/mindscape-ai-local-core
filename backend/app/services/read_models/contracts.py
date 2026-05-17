"""Manifest-backed read-model contract validation."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

CONTRACT_ID_PATTERN = re.compile(r"^[a-z0-9_]+$")
IDENTIFIER_PATTERN = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
FIELD_TYPES = {
    "boolean",
    "datetime",
    "float",
    "integer",
    "json",
    "number",
    "string",
    "text",
}
FILTER_OPERATORS = {
    "eq",
    "ilike",
    "in",
    "is_not_null",
    "is_null",
    "lte",
    "gte",
    "prefix",
}
SORT_DIRECTIONS = {"asc", "desc"}
NULLS_ORDERS = {"first", "last"}


@dataclass(frozen=True)
class ReadModelField:
    id: str
    column: str
    type: str
    nullable: bool = True


@dataclass(frozen=True)
class ReadModelFilterSpec:
    id: str
    field: str
    operator: str = "eq"
    required: bool = False


@dataclass(frozen=True)
class ReadModelSortSpec:
    id: str
    fields: tuple[dict[str, str], ...]


@dataclass(frozen=True)
class ReadModelCursorSpec:
    strategy: str
    signed: bool
    ttl_seconds: int


@dataclass(frozen=True)
class ReadModelIndexSpec:
    id: str
    columns: tuple[str, ...]
    covers_sort: tuple[str, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class ReadModelContract:
    id: str
    owner_pack: str
    contract_version: int
    table: str
    fields: dict[str, ReadModelField]
    filters: dict[str, ReadModelFilterSpec]
    sorts: dict[str, ReadModelSortSpec]
    stable_key: tuple[str, ...]
    cursor: ReadModelCursorSpec
    indexes: tuple[ReadModelIndexSpec, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class ReadModelCountContract:
    id: str
    read_model_id: str
    table: str
    key_columns: tuple[str, ...]
    supported_filter_sets: tuple[tuple[str, ...], ...]
    measures: tuple[str, ...]


def _is_contract_id(value: Any) -> bool:
    return isinstance(value, str) and CONTRACT_ID_PATTERN.match(value) is not None


def _is_identifier(value: Any) -> bool:
    return isinstance(value, str) and IDENTIFIER_PATTERN.match(value) is not None


def _append(errors: list[str], prefix: str, message: str) -> None:
    errors.append(f"{prefix}: {message}")


def _validate_unique_ids(
    items: Any,
    *,
    prefix: str,
    errors: list[str],
) -> set[str]:
    ids: set[str] = set()
    if not isinstance(items, list):
        _append(errors, prefix, "must be a list")
        return ids
    for index, item in enumerate(items):
        item_prefix = f"{prefix}[{index}]"
        if not isinstance(item, dict):
            _append(errors, item_prefix, "must be an object")
            continue
        item_id = item.get("id")
        if not _is_contract_id(item_id):
            _append(errors, f"{item_prefix}.id", "must match ^[a-z0-9_]+$")
            continue
        if item_id in ids:
            _append(errors, f"{item_prefix}.id", "must be unique")
        ids.add(item_id)
    return ids


def _field_ids(read_model: dict[str, Any], prefix: str, errors: list[str]) -> set[str]:
    fields = read_model.get("fields")
    ids = _validate_unique_ids(fields, prefix=f"{prefix}.fields", errors=errors)
    if not isinstance(fields, list):
        return ids
    for index, item in enumerate(fields):
        if not isinstance(item, dict):
            continue
        item_prefix = f"{prefix}.fields[{index}]"
        if not _is_identifier(item.get("column")):
            _append(errors, f"{item_prefix}.column", "must be a SQL identifier")
        field_type = item.get("type")
        if field_type not in FIELD_TYPES:
            _append(errors, f"{item_prefix}.type", "must be a supported field type")
        nullable = item.get("nullable")
        if nullable is not None and type(nullable) is not bool:
            _append(errors, f"{item_prefix}.nullable", "must be a boolean")
    return ids


def _validate_filters(
    read_model: dict[str, Any],
    prefix: str,
    field_ids: set[str],
    errors: list[str],
) -> set[str]:
    filters = read_model.get("filters", [])
    ids = _validate_unique_ids(filters, prefix=f"{prefix}.filters", errors=errors)
    if not isinstance(filters, list):
        return ids
    for index, item in enumerate(filters):
        if not isinstance(item, dict):
            continue
        item_prefix = f"{prefix}.filters[{index}]"
        if item.get("field") not in field_ids:
            _append(errors, f"{item_prefix}.field", "must reference a declared field")
        operator = item.get("operator", "eq")
        if operator not in FILTER_OPERATORS:
            _append(errors, f"{item_prefix}.operator", "must be a supported operator")
        required = item.get("required")
        if required is not None and type(required) is not bool:
            _append(errors, f"{item_prefix}.required", "must be a boolean")
    return ids


def _validate_sorts(
    read_model: dict[str, Any],
    prefix: str,
    field_ids: set[str],
    stable_key: list[str],
    errors: list[str],
) -> set[str]:
    sorts = read_model.get("sorts")
    sort_ids = _validate_unique_ids(sorts, prefix=f"{prefix}.sorts", errors=errors)
    if not isinstance(sorts, list):
        return sort_ids
    stable_key_set = set(stable_key)
    for index, item in enumerate(sorts):
        if not isinstance(item, dict):
            continue
        item_prefix = f"{prefix}.sorts[{index}]"
        sort_fields = item.get("fields")
        if not isinstance(sort_fields, list) or not sort_fields:
            _append(errors, f"{item_prefix}.fields", "must be a non-empty list")
            continue
        field_names: list[str] = []
        for field_index, sort_field in enumerate(sort_fields):
            field_prefix = f"{item_prefix}.fields[{field_index}]"
            if not isinstance(sort_field, dict):
                _append(errors, field_prefix, "must be an object")
                continue
            field_name = sort_field.get("field")
            if field_name not in field_ids:
                _append(errors, f"{field_prefix}.field", "must reference a declared field")
            else:
                field_names.append(field_name)
            if sort_field.get("direction") not in SORT_DIRECTIONS:
                _append(errors, f"{field_prefix}.direction", "must be asc or desc")
            nulls = sort_field.get("nulls")
            if nulls is not None and nulls not in NULLS_ORDERS:
                _append(errors, f"{field_prefix}.nulls", "must be first or last")
        if stable_key_set and not stable_key_set.issubset(set(field_names)):
            _append(errors, item_prefix, "sort must include stable_key fields as tiebreakers")
    return sort_ids


def _validate_cursor(read_model: dict[str, Any], prefix: str, errors: list[str]) -> None:
    cursor = read_model.get("cursor")
    if not isinstance(cursor, dict):
        _append(errors, f"{prefix}.cursor", "must be an object")
        return
    if cursor.get("strategy") != "keyset":
        _append(errors, f"{prefix}.cursor.strategy", "must be keyset")
    if cursor.get("signed") is not True:
        _append(errors, f"{prefix}.cursor.signed", "must be true")
    ttl_seconds = cursor.get("ttl_seconds")
    if type(ttl_seconds) is not int or ttl_seconds <= 0:
        _append(errors, f"{prefix}.cursor.ttl_seconds", "must be a positive integer")


def _validate_indexes(
    read_model: dict[str, Any],
    prefix: str,
    field_ids: set[str],
    sort_ids: set[str],
    errors: list[str],
) -> None:
    indexes = read_model.get("indexes")
    if not isinstance(indexes, list) or not indexes:
        _append(errors, f"{prefix}.indexes", "must be a non-empty list")
        return
    _validate_unique_ids(indexes, prefix=f"{prefix}.indexes", errors=errors)
    covered_sort_ids: set[str] = set()
    for index, item in enumerate(indexes):
        if not isinstance(item, dict):
            continue
        item_prefix = f"{prefix}.indexes[{index}]"
        columns = item.get("columns")
        if not isinstance(columns, list) or not columns:
            _append(errors, f"{item_prefix}.columns", "must be a non-empty list")
        else:
            for column in columns:
                if column not in field_ids:
                    _append(errors, f"{item_prefix}.columns", "must reference declared fields")
                    break
        covers_sort = item.get("covers_sort", [])
        if covers_sort is None:
            covers_sort = []
        if not isinstance(covers_sort, list):
            _append(errors, f"{item_prefix}.covers_sort", "must be a list")
            continue
        for sort_id in covers_sort:
            if sort_id not in sort_ids:
                _append(errors, f"{item_prefix}.covers_sort", "must reference declared sorts")
            else:
                covered_sort_ids.add(sort_id)
    missing_sorts = sort_ids - covered_sort_ids
    if missing_sorts:
        _append(errors, f"{prefix}.indexes", f"missing coverage for sorts: {sorted(missing_sorts)}")


def _validate_count_models(
    manifest: dict[str, Any],
    read_model_ids: set[str],
    errors: list[str],
) -> set[str]:
    count_models = manifest.get("count_models", [])
    if count_models is None:
        count_models = []
    ids = _validate_unique_ids(count_models, prefix="count_models", errors=errors)
    if not isinstance(count_models, list):
        return ids
    for index, item in enumerate(count_models):
        if not isinstance(item, dict):
            continue
        prefix = f"count_models[{index}]"
        if item.get("read_model_id") not in read_model_ids:
            _append(errors, f"{prefix}.read_model_id", "must reference read_models[].id")
        if not _is_identifier(item.get("table")):
            _append(errors, f"{prefix}.table", "must be a SQL identifier")
        key_columns = item.get("key_columns")
        if not isinstance(key_columns, list) or not key_columns or any(
            not _is_identifier(column) for column in key_columns
        ):
            _append(errors, f"{prefix}.key_columns", "must be a non-empty SQL identifier list")
        filter_sets = item.get("supported_filter_sets")
        if not isinstance(filter_sets, list) or not filter_sets:
            _append(errors, f"{prefix}.supported_filter_sets", "must be a non-empty list")
        else:
            for filter_set in filter_sets:
                if not isinstance(filter_set, list) or any(
                    not _is_contract_id(filter_id) for filter_id in filter_set
                ):
                    _append(
                        errors,
                        f"{prefix}.supported_filter_sets",
                        "must contain filter id lists",
                    )
                    break
        measures = item.get("measures")
        if not isinstance(measures, list) or not measures or any(
            not _is_identifier(measure) for measure in measures
        ):
            _append(errors, f"{prefix}.measures", "must be a non-empty SQL identifier list")
    return ids


def validate_manifest_read_models(manifest: dict[str, Any]) -> list[str]:
    """Return semantic read-model contract validation errors."""

    errors: list[str] = []
    read_models = manifest.get("read_models", [])
    if read_models is None:
        read_models = []
    read_model_ids = _validate_unique_ids(read_models, prefix="read_models", errors=errors)
    if not isinstance(read_models, list):
        return errors
    owner_pack = manifest.get("code")
    for index, read_model in enumerate(read_models):
        prefix = f"read_models[{index}]"
        if not isinstance(read_model, dict):
            continue
        if read_model.get("owner_pack") != owner_pack:
            _append(errors, f"{prefix}.owner_pack", "must equal manifest code")
        version = read_model.get("contract_version")
        if type(version) is not int or version <= 0:
            _append(errors, f"{prefix}.contract_version", "must be a positive integer")
        if not _is_identifier(read_model.get("table")):
            _append(errors, f"{prefix}.table", "must be a SQL identifier")
        field_ids = _field_ids(read_model, prefix, errors)
        stable_key = read_model.get("stable_key")
        if not isinstance(stable_key, list) or not stable_key:
            _append(errors, f"{prefix}.stable_key", "must be a non-empty list")
            stable_key = []
        else:
            for key in stable_key:
                if key not in field_ids:
                    _append(errors, f"{prefix}.stable_key", "must reference declared fields")
                    break
        scope = read_model.get("scope")
        if not isinstance(scope, dict):
            _append(errors, f"{prefix}.scope", "must be an object")
        else:
            required_filters = scope.get("required_filters")
            if not isinstance(required_filters, list) or not required_filters:
                _append(errors, f"{prefix}.scope.required_filters", "must be a non-empty list")
        _validate_filters(read_model, prefix, field_ids, errors)
        sort_ids = _validate_sorts(read_model, prefix, field_ids, stable_key, errors)
        _validate_cursor(read_model, prefix, errors)
        _validate_indexes(read_model, prefix, field_ids, sort_ids, errors)

    count_models = manifest.get("count_models", []) or []
    count_models_by_id = {
        count_model.get("id"): count_model
        for count_model in count_models
        if isinstance(count_model, dict) and isinstance(count_model.get("id"), str)
    }
    count_model_ids = _validate_count_models(manifest, read_model_ids, errors)
    budgets = manifest.get("runtime_read_path_budgets") or []
    if isinstance(budgets, list):
        for index, budget in enumerate(budgets):
            if not isinstance(budget, dict):
                continue
            prefix = f"runtime_read_path_budgets[{index}]"
            read_model_id = budget.get("read_model_id")
            count_model_id = budget.get("count_model_id")
            if read_model_id is not None:
                if read_model_id not in read_model_ids:
                    _append(errors, f"{prefix}.read_model_id", "must reference read_models[].id")
                if budget.get("endpoint_class") == "ui_list" and budget.get("db_read_model") == "projection":
                    if count_model_id not in count_model_ids:
                        _append(
                            errors,
                            f"{prefix}.count_model_id",
                            "must reference count_models[].id",
                        )
                    elif count_models_by_id[count_model_id].get("read_model_id") != read_model_id:
                        _append(
                            errors,
                            f"{prefix}.count_model_id",
                            "must reference a count model for the same read_model_id",
                        )
                forbidden_sources = budget.get("forbidden_sources")
                if not isinstance(forbidden_sources, list) or not forbidden_sources:
                    _append(errors, f"{prefix}.forbidden_sources", "must be a non-empty list")
                else:
                    for source in forbidden_sources:
                        if not isinstance(source, dict):
                            _append(
                                errors,
                                f"{prefix}.forbidden_sources",
                                "read-model budgets must use {relation, columns} objects",
                            )
                            break
                        if not _is_identifier(source.get("relation")):
                            _append(
                                errors,
                                f"{prefix}.forbidden_sources.relation",
                                "must be a SQL identifier",
                            )
                        columns = source.get("columns")
                        if not isinstance(columns, list) or not columns or any(
                            not _is_identifier(column) for column in columns
                        ):
                            _append(
                                errors,
                                f"{prefix}.forbidden_sources.columns",
                                "must be a non-empty SQL identifier list",
                            )
            elif count_model_id is not None:
                _append(errors, f"{prefix}.count_model_id", "requires read_model_id")
    return errors
