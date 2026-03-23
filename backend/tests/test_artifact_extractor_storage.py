import os
import sys
from types import SimpleNamespace

repo_root = os.path.join(os.path.dirname(__file__), "..", "..")
backend_root = os.path.join(repo_root, "backend")
sys.path.insert(0, repo_root)
sys.path.insert(0, backend_root)

from backend.app.services import artifact_extractor as canonical_extractor
from backend.app.services.artifact_extractor_core import storage
from backend.app.services.conversation import artifact_extractor as shim_extractor


def _make_store(*, versions=None, workspace=None):
    versions = versions or []
    workspace = workspace or SimpleNamespace(id="ws-1")
    artifacts = [
        SimpleNamespace(
            artifact_type=SimpleNamespace(value="draft"),
            metadata={"version": version},
        )
        for version in versions
    ]
    return SimpleNamespace(
        workspaces=SimpleNamespace(get_workspace=lambda _workspace_id: workspace),
        artifacts=SimpleNamespace(
            list_artifacts_by_playbook=lambda _workspace_id, _playbook_code: artifacts
        ),
    )


def test_conversation_artifact_extractor_reexports_canonical_class():
    assert shim_extractor.ArtifactExtractor is canonical_extractor.ArtifactExtractor
    assert shim_extractor._utc_now is canonical_extractor._utc_now


def test_generate_artifact_filename_uses_next_version_and_default_extension():
    filename = storage.generate_artifact_filename(
        store=_make_store(versions=[1, 3]),
        workspace_id="ws-1",
        playbook_code="content_drafting",
        artifact_type="draft",
        title="Draft / Title: 01",
        timestamp="20260324-120000",
    )

    assert filename == "draft-title-01-v4-20260324-120000.md"


def test_check_file_conflict_returns_suggested_version(tmp_path):
    target = tmp_path / "draft-v1-20260324-120000.md"
    target.write_text("existing", encoding="utf-8")

    conflict = storage.check_file_conflict(
        store=_make_store(versions=[1, 2]),
        target_path=target,
        workspace_id="ws-1",
        playbook_code="content_drafting",
        artifact_type="draft",
    )

    assert conflict == {"has_conflict": True, "suggested_version": 3}


def test_write_artifact_file_atomic_writes_bytes(tmp_path):
    target = tmp_path / "artifact.txt"

    storage.write_artifact_file_atomic(
        content=b"hello artifact",
        target_path=target,
    )

    assert target.read_bytes() == b"hello artifact"


def test_get_artifact_storage_path_uses_resolver_and_validation(monkeypatch, tmp_path):
    resolved_path = tmp_path / "artifacts" / "drafts"
    calls = {}

    def fake_resolver(**kwargs):
        calls["resolver"] = kwargs
        return resolved_path

    monkeypatch.setattr(
        storage.StoragePathResolver,
        "get_artifact_storage_path",
        fake_resolver,
    )
    monkeypatch.setattr(storage, "get_allowed_directories", lambda: [str(tmp_path)])
    monkeypatch.setattr(
        storage,
        "validate_path_in_allowed_directories",
        lambda path, allowed: path == resolved_path and allowed == [str(tmp_path)],
    )

    result = storage.get_artifact_storage_path(
        store=_make_store(),
        workspace_id="ws-1",
        playbook_code="content_drafting",
        intent_id="intent-1",
        artifact_type="draft",
    )

    assert result == resolved_path
    assert calls["resolver"]["playbook_code"] == "content_drafting"
    assert calls["resolver"]["intent_id"] == "intent-1"


def test_extract_version_from_filename_parses_generated_pattern():
    assert storage.extract_version_from_filename("draft-v12-20260324-120000.md") == 12
    assert storage.extract_version_from_filename("draft-20260324-120000.md") is None
