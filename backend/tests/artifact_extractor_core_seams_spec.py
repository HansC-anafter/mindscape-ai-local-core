from contextlib import AbstractContextManager, nullcontext
from dataclasses import dataclass
from pathlib import Path

from backend.app.models.workspace import ArtifactType, PrimaryActionType
from backend.app.services.artifact_extractor_core.extractors import (
    extract_content_drafting_artifact,
    extract_daily_planning_artifact,
    extract_generic_artifact,
    extract_major_proposal_artifact,
)


@dataclass
class FakeTask:
    workspace_id: str = "workspace-1"
    id: str = "task-1"
    execution_id: str = "execution-1"


class FakeArtifactService:
    def __init__(self, root: Path) -> None:
        self.root = root
        self.write_calls = []

    def _get_artifact_storage_path(
        self,
        *,
        workspace_id: str,
        playbook_code: str,
        intent_id: str | None,
        artifact_type: str,
    ) -> Path:
        path = self.root / workspace_id / playbook_code / (intent_id or "none") / artifact_type
        path.mkdir(parents=True, exist_ok=True)
        return path

    def _generate_artifact_filename(
        self,
        *,
        workspace_id: str,
        playbook_code: str,
        artifact_type: str,
        title: str,
        version: int | None = None,
    ) -> str:
        del workspace_id, playbook_code
        suffix = {
            ArtifactType.CHECKLIST.value: ".json",
            ArtifactType.DOCX.value: ".docx",
            ArtifactType.AUDIO.value: ".mp3",
        }.get(artifact_type, ".txt")
        safe_title = title.lower().replace(" ", "-")
        version_suffix = f"-v{version}" if version else ""
        return f"{safe_title}{version_suffix}{suffix}"

    def _check_file_conflict(self, **kwargs) -> dict[str, bool]:
        del kwargs
        return {"has_conflict": False}

    def _write_artifact_file_atomic(self, content_bytes: bytes, target_path: Path) -> None:
        target_path.parent.mkdir(parents=True, exist_ok=True)
        target_path.write_bytes(content_bytes)
        self.write_calls.append(target_path)

    def _file_lock(self, storage_dir: Path) -> AbstractContextManager[None]:
        del storage_dir
        return nullcontext()


def test_content_drafting_writes_generated_artifact(tmp_path: Path) -> None:
    service = FakeArtifactService(tmp_path)
    artifact = extract_content_drafting_artifact(
        service,
        FakeTask(),
        {
            "title": "Draft Title",
            "summary": "Draft summary",
            "content": "Generated body",
            "format": "brief",
            "tags": ["draft"],
        },
        "intent-1",
    )

    assert artifact.artifact_type == ArtifactType.DRAFT
    assert artifact.primary_action_type == PrimaryActionType.COPY
    assert artifact.content["content"] == "Generated body"
    assert artifact.metadata["output_type"] == "draft"
    assert Path(artifact.storage_ref).read_text() == "Generated body"


def test_major_proposal_copies_source_file(tmp_path: Path) -> None:
    service = FakeArtifactService(tmp_path)
    source_path = tmp_path / "source.docx"
    source_path.write_bytes(b"proposal")

    artifact = extract_major_proposal_artifact(
        service,
        FakeTask(),
        {
            "title": "Proposal",
            "summary": "Generated proposal",
            "file_path": str(source_path),
        },
        "intent-1",
    )

    assert artifact.artifact_type == ArtifactType.DOCX
    assert artifact.primary_action_type == PrimaryActionType.DOWNLOAD
    assert artifact.content["original_path"] == str(source_path)
    assert Path(artifact.storage_ref).read_bytes() == b"proposal"


def test_daily_planning_fallback_preserves_error_metadata(tmp_path: Path) -> None:
    service = FakeArtifactService(tmp_path)
    artifact = extract_daily_planning_artifact(
        service,
        FakeTask(),
        {
            "title": "Task extraction completed",
            "extraction_error": "No actionable tasks found",
        },
        "intent-1",
    )

    assert artifact.artifact_type == ArtifactType.CHECKLIST
    assert artifact.content["total_count"] == 1
    assert "No actionable tasks found" in artifact.content["tasks"][0]["title"]
    assert artifact.metadata["source"] == "daily_planning"
    assert Path(artifact.storage_ref).exists()


def test_generic_extraction_writes_draft_when_storage_ref_missing(tmp_path: Path) -> None:
    service = FakeArtifactService(tmp_path)
    artifact = extract_generic_artifact(
        service,
        FakeTask(),
        {
            "title": "Generic Output",
            "summary": "Generic summary",
            "content": "Generic content",
        },
        "custom_playbook",
        "intent-1",
    )

    assert artifact.artifact_type == ArtifactType.DRAFT
    assert artifact.primary_action_type == PrimaryActionType.COPY
    assert artifact.metadata["source"] == "generic_extraction"
    assert artifact.metadata["playbook_code"] == "custom_playbook"
    assert Path(artifact.storage_ref).read_text() == "Generic content"


def test_public_facade_exports_existing_helpers() -> None:
    from backend.app.services.artifact_extractor_core import extractors

    assert callable(extractors.extract_daily_planning_artifact)
    assert callable(extractors.extract_content_drafting_artifact)
    assert callable(extractors.extract_major_proposal_artifact)
    assert callable(extractors.extract_campaign_asset_artifact)
    assert callable(extractors.extract_audio_artifact)
    assert callable(extractors.extract_generic_artifact)
