from backend.app.services.read_models.contracts import validate_manifest_read_models


def _read_model():
    return {
        "id": "demo_targets",
        "owner_pack": "demo",
        "contract_version": 1,
        "table": "demo_target_projection",
        "fields": [
            {"id": "workspace_id", "column": "workspace_id", "type": "string", "nullable": False},
            {"id": "handle", "column": "handle", "type": "string", "nullable": False},
            {"id": "follower_count", "column": "follower_count", "type": "integer"},
        ],
        "filters": [
            {"id": "workspace_id", "field": "workspace_id", "operator": "eq", "required": True},
        ],
        "sorts": [
            {
                "id": "score_desc",
                "fields": [
                    {"field": "follower_count", "direction": "desc", "nulls": "last"},
                    {"field": "handle", "direction": "asc"},
                ],
            },
        ],
        "stable_key": ["handle"],
        "scope": {"required_filters": ["workspace_id"]},
        "cursor": {"strategy": "keyset", "signed": True, "ttl_seconds": 900},
        "indexes": [
            {
                "id": "demo_targets_followers_idx",
                "columns": ["workspace_id", "follower_count", "handle"],
                "covers_sort": ["score_desc"],
            },
        ],
    }


def _count_model():
    return {
        "id": "demo_target_counts",
        "read_model_id": "demo_targets",
        "table": "demo_target_count_projection",
        "key_columns": ["workspace_id"],
        "supported_filter_sets": [["workspace_id"]],
        "measures": ["total_targets"],
    }


def _budget(**overrides):
    budget = {
        "id": "demo_targets_list",
        "endpoint_class": "ui_list",
        "db_read_model": "projection",
        "read_model_id": "demo_targets",
        "count_model_id": "demo_target_counts",
        "forbidden_sources": [{"relation": "demo_raw_targets", "columns": ["payload"]}],
    }
    budget.update(overrides)
    return budget


def _manifest(**overrides):
    manifest = {
        "code": "demo",
        "read_models": [_read_model()],
        "count_models": [_count_model()],
        "runtime_read_path_budgets": [_budget()],
    }
    manifest.update(overrides)
    return manifest


def test_validate_manifest_read_models_accepts_valid_contract():
    assert validate_manifest_read_models(_manifest()) == []


def test_validate_manifest_read_models_rejects_legacy_forbidden_source_on_read_model_budget():
    errors = validate_manifest_read_models(
        _manifest(runtime_read_path_budgets=[_budget(forbidden_sources=["demo_raw_targets.payload"])]),
    )

    assert any("read-model budgets must use {relation, columns} objects" in error for error in errors)


def test_validate_manifest_read_models_rejects_missing_count_model_for_ui_projection():
    errors = validate_manifest_read_models(
        _manifest(runtime_read_path_budgets=[_budget(count_model_id=None)]),
    )

    assert any("count_model_id" in error and "count_models" in error for error in errors)


def test_validate_manifest_read_models_rejects_sort_without_stable_key_tiebreaker():
    read_model = _read_model()
    read_model["sorts"] = [
        {
            "id": "score_desc",
            "fields": [
                {"field": "follower_count", "direction": "desc", "nulls": "last"},
            ],
        },
    ]
    errors = validate_manifest_read_models(_manifest(read_models=[read_model]))

    assert any("sort must include stable_key fields" in error for error in errors)
