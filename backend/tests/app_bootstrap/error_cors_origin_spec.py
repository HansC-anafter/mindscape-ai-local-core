from backend.app.app_bootstrap import cors


def test_error_cors_origin_uses_cached_origins_without_dynamic_lookup(monkeypatch):
    cors._CACHED_CORS_ORIGINS = ["http://localhost:8300"]

    def fail_dynamic_lookup():
        raise AssertionError("error CORS resolution must not load dynamic config")

    monkeypatch.setattr(cors, "get_cors_origins", fail_dynamic_lookup)

    assert cors.resolve_error_cors_origin("http://localhost:8300") == "http://localhost:8300"
    assert cors.resolve_error_cors_origin("http://evil.example") == "http://localhost:8300"
