from pathlib import Path


LOCAL_CORE_APP = Path(__file__).resolve().parents[2] / "app"
ALLOWED_CREATE_ENGINE_FILES = {
    LOCAL_CORE_APP / "database" / "engine_factory.py",
    LOCAL_CORE_APP / "services" / "migrations" / "orchestrator.py",
}
FORBIDDEN_SNIPPETS = (
    "create_engine(get_postgres_url_core(",
    "create_engine(DATABASE_URL",
    "create_engine(_verify_db_url",
)


def test_local_core_host_code_has_no_unclassified_ad_hoc_engines():
    offenders: list[str] = []
    for path in LOCAL_CORE_APP.rglob("*.py"):
        if "/capabilities/" in path.as_posix():
            continue
        if path in ALLOWED_CREATE_ENGINE_FILES:
            continue
        text = path.read_text(encoding="utf-8")
        for snippet in FORBIDDEN_SNIPPETS:
            if snippet in text:
                offenders.append(f"{path}:{snippet}")

    assert offenders == []
