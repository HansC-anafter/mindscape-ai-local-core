from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path


def _load_migration_module():
    repo_root = Path(__file__).resolve().parents[3]
    module_path = (
        repo_root
        / "backend"
        / "alembic_migrations"
        / "versions"
        / "20260125000000_add_lens_and_artifacts.py"
    )
    spec = spec_from_file_location("test_lens_and_artifacts_migration", module_path)
    module = module_from_spec(spec)
    assert spec is not None
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


class _FakeInspector:
    def get_table_names(self):
        return [
            "mind_lens_schemas",
            "lens_specs",
            "mind_lens_instances",
            "artifacts",
        ]

    def get_indexes(self, table_name):
        indexes = {
            "mind_lens_schemas": [{"name": "idx_mind_lens_schemas_role"}],
            "lens_specs": [{"name": "idx_lens_specs_category"}],
            "mind_lens_instances": [
                {"name": "idx_mind_lens_instances_owner"},
                {"name": "idx_mind_lens_instances_role"},
                {"name": "idx_mind_lens_instances_schema"},
            ],
            "artifacts": [
                {"name": "idx_artifacts_created_at"},
                {"name": "idx_artifacts_execution"},
                {"name": "idx_artifacts_intent"},
                {"name": "idx_artifacts_playbook"},
                {"name": "idx_artifacts_step"},
                {"name": "idx_artifacts_task"},
                {"name": "idx_artifacts_thread"},
                {"name": "idx_artifacts_workspace"},
                {"name": "idx_artifacts_workspace_created_at"},
                {"name": "idx_artifacts_workspace_intent"},
            ],
        }
        return indexes[table_name]


def test_upgrade_skips_existing_lens_and_artifact_tables_and_indexes(monkeypatch):
    module = _load_migration_module()
    create_table_calls = []
    create_index_calls = []

    monkeypatch.setattr(module.op, "get_bind", lambda: object())
    monkeypatch.setattr(module.sa, "inspect", lambda _bind: _FakeInspector())
    monkeypatch.setattr(
        module.op,
        "create_table",
        lambda *args, **kwargs: create_table_calls.append((args, kwargs)),
    )
    monkeypatch.setattr(
        module.op,
        "create_index",
        lambda *args, **kwargs: create_index_calls.append((args, kwargs)),
    )

    module.upgrade()

    assert create_table_calls == []
    assert create_index_calls == []
