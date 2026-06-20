from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]

TOUCHED_FILES = [
    "backend/app/services/validation_service.py",
    "backend/app/services/validation_service_core/__init__.py",
    "backend/app/services/validation_service_core/system_checks.py",
    "backend/app/services/validation_service_core/archive_checks.py",
    "backend/app/services/validation_service_core/manifest_checks.py",
    "backend/app/services/validation_service_core/compatibility_checks.py",
    "backend/app/services/validation_service_core/security_checks.py",
    "backend/app/services/validation_service_core/dependency_checks.py",
    "backend/tests/validation_service_seams_spec.py",
]

PRODUCTION_FILES = [path for path in TOUCHED_FILES if not path.startswith("backend/tests/")]


def read_source(relative_path: str) -> str:
    return (ROOT / relative_path).read_text(encoding="utf-8")


def test_facade_keeps_public_and_private_wrapper_contracts():
    source = read_source("backend/app/services/validation_service.py")
    for fragment in [
        "class ValidationService",
        "def validate_before_install",
        "def _validate_system_health",
        "def _check_database_connection",
        "def _check_dependency_services",
        "def _validate_mindpack_file",
        "def _validate_manifest",
        "def _validate_manifest_with_script",
        "def _validate_compatibility",
        "def _get_installed_packs",
        "def _validate_security",
        "def _validate_dependencies",
    ]:
        assert fragment in source

    moved_fragments = [
        "PostgresStoreBase",
        "redis.from_url",
        "InstalledPacksStore",
        "subprocess.run",
        "MemoryEvidenceLink",
    ]
    for fragment in moved_fragments:
        assert fragment not in source


def test_live_install_pipeline_still_uses_manifest_validator_only():
    pipeline_source = read_source("backend/app/routes/core/capability_install_core/pipeline.py")
    routes_source = read_source("backend/app/routes/core/capability_install_core/routes.py")

    assert "ManifestValidator(local_core_root)" in pipeline_source
    assert "ValidationService" not in pipeline_source
    assert "validation_service" not in pipeline_source

    assert "CapabilityInstallJobService().create_file_upload_job" in routes_source
    assert '"accepted": True' in routes_source
    assert '"status_url": job["status_url"]' in routes_source
    assert "ValidationService" not in routes_source
    assert "validation_service" not in routes_source


def test_system_helper_preserves_db_and_redis_check_contracts():
    source = read_source("backend/app/services/validation_service_core/system_checks.py")
    for fragment in [
        "PostgresStoreBase",
        "store.get_connection",
        'text("SELECT 1")',
        "redis.from_url",
        "redis_client.ping()",
        "Redis client not installed",
        "Redis not available",
        "Directory not writable",
        "Insufficient disk space",
    ]:
        assert fragment in source


def test_validation_helpers_preserve_representative_contracts():
    archive_source = read_source("backend/app/services/validation_service_core/archive_checks.py")
    manifest_source = read_source("backend/app/services/validation_service_core/manifest_checks.py")
    compatibility_source = read_source(
        "backend/app/services/validation_service_core/compatibility_checks.py"
    )
    security_source = read_source("backend/app/services/validation_service_core/security_checks.py")
    dependency_source = read_source(
        "backend/app/services/validation_service_core/dependency_checks.py"
    )

    for fragment in [
        "Mindpack file not found",
        "Invalid file extension",
        "Unsafe path in mindpack",
        "manifest.yaml not found in extracted directory",
    ]:
        assert fragment in archive_source

    for fragment in [
        "Missing required field",
        "expected semver",
        "validate_manifest.py not found, skipping advanced validation",
        "timeout=30",
        "Validation script timed out",
    ]:
        assert fragment in manifest_source

    for fragment in [
        "InstalledPacksStore",
        "store.list_installed_pack_ids",
        "already installed",
        "Missing dependency",
    ]:
        assert fragment in compatibility_source

    for fragment in [
        "Path traversal detected",
        "Absolute path detected",
        "Unexpected executable file",
    ]:
        assert fragment in security_source

    for fragment in [
        "Tool dependency not found",
        "Required API key not configured",
        "core_llm.",
    ]:
        assert fragment in dependency_source


def test_touched_files_stay_under_large_file_gate_and_resource_rules():
    forbidden_resource_fragments = [
        "Queue(",
        "Thread(",
        "Process(",
        "create_engine(",
        "pgbouncer",
        "asyncio",
        "setInterval",
        "EventSource",
    ]
    for relative_path in TOUCHED_FILES:
        source = read_source(relative_path)
        line_count = source.count("\n")
        assert line_count <= 500, f"{relative_path} has {line_count} lines"
        assert not any("\u4e00" <= char <= "\u9fff" for char in source)
    for relative_path in PRODUCTION_FILES:
        source = read_source(relative_path)
        for fragment in forbidden_resource_fragments:
            assert fragment not in source
