import importlib.util
import json
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[3]


def _load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


report_script = _load_module(
    "postgres_ha_readiness_report",
    REPO_ROOT / "backend" / "scripts" / "postgres_ha_readiness_report.py",
)


def test_postgres_ha_readiness_report_emits_json_schema(monkeypatch, capsys):
    def fake_report(*, use_readonly_probe):
        assert use_readonly_probe is True
        return {
            "schema_version": 1,
            "primary": {
                "available": True,
                "postgres_in_recovery": False,
                "transaction_read_only": "off",
                "app_idle_in_transaction_count": 0,
            },
            "pgbouncer": {
                "available": True,
                "core_database_present": True,
                "vector_database_present": True,
                "readonly_core_database_present": True,
                "readonly_vector_database_present": True,
                "core_pool_present": True,
                "vector_pool_present": True,
                "readonly_core_pool_present": True,
                "readonly_vector_pool_present": True,
                "core_waiting": 0,
                "vector_waiting": 0,
                "readonly_core_waiting": 0,
                "readonly_vector_waiting": 0,
            },
            "replica": {"available": True},
            "postgres_in_recovery": False,
            "transaction_read_only": "off",
            "pgbouncer_core_waiting": 0,
            "pgbouncer_vector_waiting": 0,
            "replica_available": True,
            "wal_archive_mode": "on",
        }

    monkeypatch.setattr(report_script, "build_ha_readiness_report", fake_report)

    exit_code = report_script.main(["--use-readonly-probe", "--json", "--check"])
    payload = json.loads(capsys.readouterr().out)

    assert exit_code == 0
    assert payload["schema_version"] == 1
    assert payload["check_passed"] is True
    assert payload["check_errors"] == []
