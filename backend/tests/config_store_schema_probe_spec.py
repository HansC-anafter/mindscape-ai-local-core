from backend.app.services.config_store import ConfigStore


def test_config_store_schema_probe_runs_once_per_process(monkeypatch):
    calls = []
    ConfigStore._schema_ensured = False

    def fake_ensure_schema(self):
        calls.append(self)
        ConfigStore._schema_ensured = True

    monkeypatch.setattr(ConfigStore, "_ensure_schema", fake_ensure_schema)

    ConfigStore()
    ConfigStore()

    assert len(calls) == 1
