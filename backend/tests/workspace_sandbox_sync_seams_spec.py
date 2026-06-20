from pathlib import Path

import pytest

from backend.app.services.sandbox.workspace_sync_core.file_operations import (
    get_workspace_sandbox_diff,
    sync_sandbox_files_to_workspace,
    sync_workspace_files_to_sandbox,
)


ROOT = Path(__file__).resolve().parents[2]

TOUCHED_FILES = [
    "backend/app/services/sandbox/workspace_sync.py",
    "backend/app/services/sandbox/workspace_sync_core/__init__.py",
    "backend/app/services/sandbox/workspace_sync_core/filters.py",
    "backend/app/services/sandbox/workspace_sync_core/file_operations.py",
    "backend/tests/workspace_sandbox_sync_seams_spec.py",
]

PRODUCTION_FILES = [path for path in TOUCHED_FILES if not path.startswith("backend/tests/")]


class FakeSandbox:
    def __init__(self, files=None, sandbox_type="web_page"):
        self.files = dict(files or {})
        self.sandbox_type = sandbox_type
        self.writes = []
        self.synced_pages = False

    async def write_file(self, path: str, content: str) -> None:
        self.files[path] = content
        self.writes.append(path)

    async def read_file(self, path: str) -> str:
        return self.files[path]

    async def list_files(self):
        return [{"path": path} for path in sorted(self.files)]

    async def sync_pages_to_app(self) -> None:
        self.synced_pages = True


def read_source(relative_path: str) -> str:
    return (ROOT / relative_path).read_text(encoding="utf-8")


def test_canonical_routes_and_watcher_still_use_workspace_sync_facade():
    sync_routes = read_source("backend/app/routes/core/sandbox_core/sync_routes.py")
    preview_routes = read_source("backend/app/routes/core/sandbox_core/preview_routes.py")
    file_watcher = read_source("backend/app/services/sandbox/file_watcher.py")

    assert "from backend.app.services.sandbox.workspace_sync import get_workspace_sync_service" in sync_routes
    assert "from backend.app.services.sandbox.workspace_sync import get_workspace_sync_service" in preview_routes
    assert "from backend.app.services.sandbox.workspace_sync import WorkspaceSandboxSync" in file_watcher


def test_facade_keeps_public_methods_and_private_wrappers():
    source = read_source("backend/app/services/sandbox/workspace_sync.py")
    for fragment in [
        "class WorkspaceSandboxSync",
        "def get_workspace_sync_service",
        "async def ensure_sandbox_for_preview",
        "async def sync_workspace_to_sandbox",
        "async def rebuild_sandbox_from_workspace",
        "async def sync_sandbox_to_workspace",
        "async def get_sync_diff",
        "def _get_sync_directories",
        "def _should_sync_file",
        "def _is_protected",
        "async def _find_existing_sandbox",
        "async def _create_and_initialize_sandbox",
    ]:
        assert fragment in source

    for fragment in [
        "os.walk",
        "shutil.copy2",
        "await sandbox.list_files",
        "source_file.read_text",
        "target_path.write_text",
    ]:
        assert fragment not in source


def test_helper_modules_preserve_filter_and_file_operation_contracts():
    filters_source = read_source(
        "backend/app/services/sandbox/workspace_sync_core/filters.py"
    )
    file_ops_source = read_source(
        "backend/app/services/sandbox/workspace_sync_core/file_operations.py"
    )

    for fragment in [
        "PROTECTED_PATTERNS",
        "DEFAULT_SYNC_DIRECTORIES",
        "package.json",
        "node_modules/",
        "fnmatch.fnmatch",
        "os.walk",
        "should_sync_file",
    ]:
        assert fragment in filters_source

    for fragment in [
        "sync_workspace_files_to_sandbox",
        "sync_sandbox_files_to_workspace",
        "get_workspace_sandbox_diff",
        "await sandbox.write_file",
        "await sandbox.read_file",
        "await sandbox.list_files",
        "shutil.copy2",
        '".backup"',
        "await sandbox.sync_pages_to_app",
    ]:
        assert fragment in file_ops_source


@pytest.mark.asyncio
async def test_workspace_to_sandbox_helper_syncs_allowed_files(tmp_path):
    workspace = tmp_path / "workspace"
    (workspace / "pages").mkdir(parents=True)
    (workspace / "pages" / "home.md").write_text("hello", encoding="utf-8")
    (workspace / "package.json").write_text("{}", encoding="utf-8")

    sandbox = FakeSandbox()
    synced = await sync_workspace_files_to_sandbox(workspace, sandbox, ["pages"])

    assert synced == ["pages/home.md"]
    assert sandbox.files["pages/home.md"] == "hello"
    assert "package.json" not in sandbox.files
    assert sandbox.synced_pages is True


@pytest.mark.asyncio
async def test_sandbox_to_workspace_helper_preserves_backup_behavior(tmp_path):
    workspace = tmp_path / "workspace"
    (workspace / "pages").mkdir(parents=True)
    (workspace / "pages" / "home.md").write_text("old", encoding="utf-8")

    sandbox = FakeSandbox(
        {
            "pages/home.md": "new",
            "package.json": "{}",
        }
    )
    result = await sync_sandbox_files_to_workspace(
        workspace,
        sandbox,
        ["pages"],
        create_backup=True,
    )

    assert result == {
        "synced_files": ["pages/home.md"],
        "backed_up_files": ["pages/home.md"],
        "status": "success",
    }
    assert (workspace / "pages" / "home.md").read_text(encoding="utf-8") == "new"
    assert (workspace / "pages" / "home.md.backup").read_text(encoding="utf-8") == "old"
    assert not (workspace / "package.json").exists()


@pytest.mark.asyncio
async def test_diff_helper_reports_added_modified_deleted_and_unchanged(tmp_path):
    workspace = tmp_path / "workspace"
    (workspace / "pages").mkdir(parents=True)
    (workspace / "pages" / "same.md").write_text("same", encoding="utf-8")
    (workspace / "pages" / "changed.md").write_text("old", encoding="utf-8")
    (workspace / "pages" / "deleted.md").write_text("gone", encoding="utf-8")

    sandbox = FakeSandbox(
        {
            "pages/same.md": "same",
            "pages/changed.md": "new",
            "pages/added.md": "added",
        }
    )
    diff = await get_workspace_sandbox_diff(workspace, sandbox, ["pages"])

    assert set(diff["added"]) == {"pages/added.md"}
    assert set(diff["modified"]) == {"pages/changed.md"}
    assert set(diff["deleted"]) == {"pages/deleted.md"}
    assert set(diff["unchanged"]) == {"pages/same.md"}
    assert diff["sandbox_type"] == "web_page"
    assert diff["sync_directories"] == ["pages"]


def test_touched_files_stay_under_large_file_gate_and_resource_rules():
    forbidden_resource_fragments = [
        "Queue(",
        "Thread(",
        "Process(",
        "create_engine(",
        "pgbouncer",
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
