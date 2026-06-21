from typing import Any, Dict, List

from .models import ValidationError
from .patterns import (
    AOL_FIELD_PATTERN,
    CONTRACT_ID_PATTERN,
    RUNTIME_READ_PATH_DB_MODELS,
    RUNTIME_READ_PATH_DENY_LIST_REQUIRED_CLASSES,
    RUNTIME_READ_PATH_ENDPOINT_CLASSES,
    RUNTIME_READ_PATH_REQUIRED_FIELDS,
    _manifest_error,
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
