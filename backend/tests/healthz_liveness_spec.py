from pathlib import Path


MAIN_SOURCE = Path(__file__).resolve().parents[1] / "app" / "main.py"
LIFECYCLE_SOURCE = (
    Path(__file__).resolve().parents[1] / "app" / "app_bootstrap" / "lifecycle.py"
)


def _healthz_source() -> str:
    source = MAIN_SOURCE.read_text()
    start = source.index('@app.get("/healthz")')
    end = source.index("# Connect modular bootstrap components")
    return source[start:end]


def test_healthz_is_dependency_free_liveness():
    source = _healthz_source()
    banned_terms = (
        "SystemHealthChecker",
        "_check_ocr_service",
        "_check_llm_configuration",
        "_check_vector_db",
        "object_index",
        "check_workspace_health",
    )

    for term in banned_terms:
        assert term not in source

    assert '"status": "ok"' in source
    assert "get_backend_runtime_role()" in source
    assert "should_enable_uvicorn_reload()" in source


def test_healthz_route_is_registered_before_bulk_api_routes():
    source = MAIN_SOURCE.read_text()

    assert source.index('@app.get("/healthz")') < source.index("register_all_routes(app)")


def test_post_ready_warmups_wait_for_server_bind_grace():
    source = LIFECYCLE_SOURCE.read_text()

    assert "MINDSCAPE_POST_READY_BIND_GRACE_SECONDS" in source
    assert "_run_post_ready_heavy_work" in source
    assert source.index("_wait_for_post_ready_bind_grace(\"tool-rag-post-ready-warmup\")") < source.index(
        "refresh_tool_rag_corpus("
    )
    assert source.index("_wait_for_post_ready_bind_grace(") < source.index(
        "\"playbook-registry-post-ready-warmup\""
    )
    assert "asyncio.run(" in source
