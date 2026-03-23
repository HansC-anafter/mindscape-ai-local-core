import os
import sys
from contextlib import nullcontext
from pathlib import Path
from types import SimpleNamespace

repo_root = os.path.join(os.path.dirname(__file__), "..", "..")
backend_root = os.path.join(repo_root, "backend")
sys.path.insert(0, repo_root)
sys.path.insert(0, backend_root)

from backend.app.services import artifact_extractor as canonical_extractor
from backend.app.services.artifact_extractor_core import extractors


def _make_task():
    return SimpleNamespace(
        id="task-1",
        workspace_id="ws-1",
        execution_id="exec-1",
    )


class _StubService:
    def __init__(self, base_dir: Path):
        self.base_dir = base_dir

    def _get_artifact_storage_path(self, **_kwargs):
        self.base_dir.mkdir(parents=True, exist_ok=True)
        return self.base_dir

    def _generate_artifact_filename(self, **kwargs):
        return f"{kwargs['playbook_code']}-{kwargs.get('version') or 1}.txt"

    def _check_file_conflict(self, **_kwargs):
        return {"has_conflict": False, "suggested_version": None}

    def _write_artifact_file_atomic(self, content, target_path):
        target_path.parent.mkdir(parents=True, exist_ok=True)
        target_path.write_bytes(content)

    def _file_lock(self, _path):
        return nullcontext()


def test_extract_daily_planning_artifact_creates_error_checklist_and_file(tmp_path):
    service = _StubService(tmp_path / "artifacts")
    artifact = extractors.extract_daily_planning_artifact(
        service,
        _make_task(),
        {
            "title": "Planning Run",
            "summary": "",
            "tasks": [],
            "extraction_error": "Nothing actionable found",
        },
        "intent-1",
    )

    assert artifact is not None
    assert artifact.title == "Planning Run"
    assert artifact.artifact_type.value == "checklist"
    assert artifact.content["tasks"][0]["title"].startswith("⚠️")
    assert artifact.storage_ref is not None
    assert Path(artifact.storage_ref).exists()


def test_extract_content_drafting_summary_artifact_formats_key_points():
    artifact = extractors.extract_content_drafting_artifact(
        service=SimpleNamespace(),
        task=_make_task(),
        execution_result={
            "summary": "Summary generated",
            "content": "",
            "key_points": ["Point A", "Point B"],
            "themes": ["Theme X"],
        },
        intent_id=None,
    )

    assert artifact is not None
    assert artifact.storage_ref is None
    assert artifact.metadata["output_type"] == "summary"
    assert "Key Points" in artifact.content["content"]
    assert "Themes" in artifact.content["content"]


def test_extract_generic_artifact_returns_none_when_no_extractable_fields():
    artifact = extractors.extract_generic_artifact(
        service=SimpleNamespace(),
        task=_make_task(),
        execution_result={},
        playbook_code="unknown_playbook",
        intent_id=None,
    )

    assert artifact is None


def test_artifact_extractor_wrapper_delegates_to_content_drafting_helper():
    extractor = canonical_extractor.ArtifactExtractor(store=SimpleNamespace())
    artifact = extractor._extract_content_drafting_artifact(
        _make_task(),
        {
            "title": "Draft",
            "summary": "Summary generated",
            "content": "",
            "key_points": ["Point A"],
        },
        None,
    )

    assert artifact is not None
    assert artifact.title == "Draft"
    assert artifact.playbook_code == "content_drafting"
