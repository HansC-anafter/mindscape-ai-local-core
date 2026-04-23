from backend.app.database.config import get_engine_kwargs


def test_get_engine_kwargs_includes_application_name(monkeypatch) -> None:
    monkeypatch.setenv("DB_POOL_SIZE", "7")
    monkeypatch.setenv("DB_MAX_OVERFLOW", "3")
    monkeypatch.setenv("DB_APPLICATION_NAME", "local-core-runner-browser")

    kwargs = get_engine_kwargs()

    assert kwargs["pool_size"] == 7
    assert kwargs["max_overflow"] == 3
    assert kwargs["connect_args"] == {
        "application_name": "local-core-runner-browser"
    }
