from __future__ import annotations

import json
from contextlib import contextmanager
from types import SimpleNamespace

import pytest

from backend.app.services.media_transport.motion_reference_profile_artifact import (
    MOTION_REFERENCE_PROFILE_ARTIFACT_CONTRACT,
    MotionReferenceProfileArtifactError,
    canonical_motion_reference_source_ref,
    resolve_motion_reference_profile_artifact,
    resolve_selected_motion_reference_profile,
)
from backend.app.services.media_transport.motion_reference_profile_artifact_store import (
    MOTION_REFERENCE_PROFILE_ARTIFACT_TYPE,
    MOTION_REFERENCE_PROFILE_OWNER_PLAYBOOK,
    MotionReferenceProfileArtifactStore,
)


class FakeArtifactStore:
    def __init__(self, artifact) -> None:
        self.artifact = artifact

    def get_artifact(self, artifact_id: str):
        return self.artifact if self.artifact and self.artifact.id == artifact_id else None

    def find_by_source_ref(self, *, workspace_id: str, source_ref: str, limit: int = 2):
        if not self.artifact or self.artifact.workspace_id != workspace_id:
            return []
        if self.artifact.metadata.get("source_ref") != source_ref:
            return []
        return [self.artifact][:limit]


def _profile() -> dict:
    return {
        "schema_version": "motion_reference_profile.v1",
        "reference_profile_id": "reference-one",
        "source_ref": "https://example.test/reference",
        "chapters": [
            {
                "chapter_id": "chapter-one",
                "feature_series": [
                    {"pose_confidence": 0.9, "body_visibility": 0.95}
                ],
            }
        ],
        "visual_evidence": [
            {
                "asset_id": "chapter-one:reference:snapshot",
                "chapter_id": "chapter-one",
                "role": "reference",
                "media_kind": "snapshot",
                "artifact_id": "reference-contact-sheet-one",
                "mime_type": "image/jpeg",
                "label": "Reference chapter representative frame",
                "time_range_ms": [0.0, 2000.0],
                "media_time_range_ms": [0.0, 2000.0],
                "capture_ms": 1000.0,
                "sprite_frame_index": 0,
                "sprite_grid_columns": 1,
                "sprite_grid_rows": 1,
                "source_ref": "https://example.test/reference",
                "lineage": "independent_reference_media_chapter_frame",
                "source_kind": "reference_asset",
            }
        ],
        "metadata": {"comparison_provenance": "independent_reference_asset"},
    }


def _artifact(path, *, workspace_id: str = "workspace-one"):
    return SimpleNamespace(
        id="artifact-one",
        workspace_id=workspace_id,
        storage_ref=str(path),
        metadata={
            "artifact_contract": MOTION_REFERENCE_PROFILE_ARTIFACT_CONTRACT,
            "reference_profile_id": "reference-one",
            "source_ref": "https://example.test/reference",
        },
    )


def test_resolves_workspace_owned_profile_from_bounded_data_path(
    tmp_path,
    monkeypatch,
) -> None:
    monkeypatch.setenv("LOCAL_CORE_DATA_DIR", str(tmp_path))
    profile_path = (
        tmp_path
        / "workspaces/workspace-one/artifacts/yogacoach/reference-profiles/reference.json"
    )
    profile_path.parent.mkdir(parents=True)
    profile_path.write_text(json.dumps(_profile()), encoding="utf-8")

    resolved = resolve_motion_reference_profile_artifact(
        artifact_store=FakeArtifactStore(_artifact(profile_path)),
        workspace_id="workspace-one",
        artifact_id="artifact-one",
    )

    assert resolved.reference_profile_id == "reference-one"
    assert resolved.chapter_count == 1
    assert resolved.storage_ref == str(profile_path.resolve())
    assert resolved.receiver_ref() == {
        "artifact_id": "artifact-one",
        "storage_ref": str(profile_path.resolve()),
        "reference_profile_id": "reference-one",
    }


def test_resolves_selected_profile_by_exact_source_ref(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("LOCAL_CORE_DATA_DIR", str(tmp_path))
    profile_path = (
        tmp_path
        / "workspaces/workspace-one/artifacts/yogacoach/reference-profiles/reference.json"
    )
    profile_path.parent.mkdir(parents=True)
    profile_path.write_text(json.dumps(_profile()), encoding="utf-8")

    resolved = resolve_selected_motion_reference_profile(
        artifact_store=FakeArtifactStore(_artifact(profile_path)),
        workspace_id="workspace-one",
        artifact_id=None,
        source_ref="https://example.test/reference",
    )

    assert resolved is not None
    assert resolved.artifact_id == "artifact-one"


def test_bilibili_tracking_url_resolves_to_canonical_video_identity(
    tmp_path,
    monkeypatch,
) -> None:
    canonical_ref = "https://www.bilibili.com/video/BV13g4y1u7di/"
    selected_ref = (
        f"{canonical_ref}?spm_id_from=333.1007.top_right_bar_window_history.content.click"
        "&vd_source=5c3570349f024462fa1179899b0a83e5"
    )
    monkeypatch.setenv("LOCAL_CORE_DATA_DIR", str(tmp_path))
    profile_path = (
        tmp_path
        / "workspaces/workspace-one/artifacts/yogacoach/reference-profiles/reference.json"
    )
    profile_path.parent.mkdir(parents=True)
    profile = _profile()
    profile["source_ref"] = canonical_ref
    profile["visual_evidence"][0]["source_ref"] = canonical_ref
    profile_path.write_text(json.dumps(profile), encoding="utf-8")
    artifact = _artifact(profile_path)
    artifact.metadata["source_ref"] = canonical_ref

    resolved = resolve_selected_motion_reference_profile(
        artifact_store=FakeArtifactStore(artifact),
        workspace_id="workspace-one",
        artifact_id=None,
        source_ref=selected_ref,
    )

    assert canonical_motion_reference_source_ref(selected_ref) == canonical_ref
    assert resolved is not None
    assert resolved.source_ref == canonical_ref


def test_rejects_selected_source_without_materialized_profile() -> None:
    with pytest.raises(
        MotionReferenceProfileArtifactError,
        match="motion_reference_profile_not_materialized",
    ):
        resolve_selected_motion_reference_profile(
            artifact_store=FakeArtifactStore(None),
            workspace_id="workspace-one",
            artifact_id=None,
            source_ref="https://example.test/reference",
        )


def test_rejects_profile_without_complete_reference_visual_coverage(
    tmp_path,
    monkeypatch,
) -> None:
    monkeypatch.setenv("LOCAL_CORE_DATA_DIR", str(tmp_path))
    profile_path = (
        tmp_path
        / "workspaces/workspace-one/artifacts/yogacoach/reference-profiles/reference.json"
    )
    profile_path.parent.mkdir(parents=True)
    profile = _profile()
    profile["visual_evidence"] = []
    profile_path.write_text(json.dumps(profile), encoding="utf-8")

    with pytest.raises(
        MotionReferenceProfileArtifactError,
        match="motion_reference_profile_visual_evidence_count_invalid",
    ):
        resolve_motion_reference_profile_artifact(
            artifact_store=FakeArtifactStore(_artifact(profile_path)),
            workspace_id="workspace-one",
            artifact_id="artifact-one",
        )


def test_source_lookup_uses_indexed_owner_scope_before_text_json_cast(
    monkeypatch,
) -> None:
    executions: list[tuple[str, dict]] = []

    class FakeConnection:
        def execute(self, statement, parameters):
            executions.append((str(statement), dict(parameters)))
            return SimpleNamespace(fetchall=lambda: [])

    @contextmanager
    def fake_connection():
        yield FakeConnection()

    store = object.__new__(MotionReferenceProfileArtifactStore)
    monkeypatch.setattr(store, "get_connection", fake_connection)

    assert store.find_by_source_ref(
        workspace_id="workspace-one",
        source_ref="https://example.test/reference",
    ) == []
    query, parameters = executions[0]
    assert "candidate.playbook_code = :playbook_code" in query
    assert "candidate.artifact_type = :artifact_type" in query
    assert "candidate.metadata::jsonb ->> 'source_ref'" in query
    assert "AND NOT EXISTS" in query
    assert "successor.metadata::jsonb" in query
    assert "->> 'source_reference_profile_id'" in query
    assert "candidate.metadata::jsonb" in query
    assert "->> 'reference_profile_id'" in query
    assert parameters["playbook_code"] == MOTION_REFERENCE_PROFILE_OWNER_PLAYBOOK
    assert parameters["artifact_type"] == MOTION_REFERENCE_PROFILE_ARTIFACT_TYPE


def test_rejects_profile_path_outside_workspace_boundary(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("LOCAL_CORE_DATA_DIR", str(tmp_path))
    profile_path = tmp_path / "outside/reference.json"
    profile_path.parent.mkdir(parents=True)
    profile_path.write_text(json.dumps(_profile()), encoding="utf-8")

    with pytest.raises(
        MotionReferenceProfileArtifactError,
        match="motion_reference_profile_storage_ref_outside_workspace",
    ):
        resolve_motion_reference_profile_artifact(
            artifact_store=FakeArtifactStore(_artifact(profile_path)),
            workspace_id="workspace-one",
            artifact_id="artifact-one",
        )


def test_rejects_cross_workspace_artifact(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("LOCAL_CORE_DATA_DIR", str(tmp_path))
    profile_path = tmp_path / "reference.json"
    profile_path.write_text(json.dumps(_profile()), encoding="utf-8")

    with pytest.raises(
        MotionReferenceProfileArtifactError,
        match="motion_reference_profile_workspace_mismatch",
    ):
        resolve_motion_reference_profile_artifact(
            artifact_store=FakeArtifactStore(
                _artifact(profile_path, workspace_id="workspace-other")
            ),
            workspace_id="workspace-one",
            artifact_id="artifact-one",
        )
