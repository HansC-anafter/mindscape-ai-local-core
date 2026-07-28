from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.app.services.media_transport.motion_reference_profile_artifact import (
    MOTION_REFERENCE_PROFILE_ARTIFACT_CONTRACT,
)


def _load_route_module():
    module_path = (
        Path(__file__).resolve().parents[1]
        / "app/routes/core/workspace/motion_reference_profiles.py"
    )
    spec = importlib.util.spec_from_file_location(
        "motion_reference_profiles_route_under_test",
        module_path,
    )
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _profile(source_ref: str) -> dict:
    return {
        "schema_version": "motion_reference_profile.v1",
        "reference_profile_id": "profile-terminal-v3",
        "source_ref": source_ref,
        "chapters": [
            {
                "chapter_id": "chapter-1",
                "title": "Warm up",
                "ts_start_ms": 0,
                "ts_end_ms": 12000,
                "confidence": 0.91,
                "feature_series": [{"pose_confidence": 0.9}],
            },
            {
                "chapter_id": "chapter-2",
                "title": "Standing flow",
                "ts_start_ms": 12000,
                "ts_end_ms": 42000,
                "confidence": 0.94,
                "feature_series": [{"pose_confidence": 0.93}],
            },
        ],
        "visual_evidence": [
            {
                "asset_id": f"{chapter_id}:snapshot",
                "chapter_id": chapter_id,
                "role": "reference",
                "source_kind": "reference_asset",
                "media_kind": "snapshot",
                "artifact_id": f"{chapter_id}:asset",
                "mime_type": "image/jpeg",
                "label": f"{chapter_id} evidence",
                "lineage": "independent_reference_media_chapter_frame",
                "source_ref": source_ref,
            }
            for chapter_id in ("chapter-1", "chapter-2")
        ],
        "metadata": {"comparison_provenance": "independent_reference_asset"},
    }


class FakeArtifactStore:
    def __init__(self, artifacts) -> None:
        self.artifacts = list(artifacts)
        self.source_lookups = 0

    def get_artifact(self, artifact_id: str):
        return next(
            (artifact for artifact in self.artifacts if artifact.id == artifact_id),
            None,
        )

    def find_by_source_ref(self, *, workspace_id: str, source_ref: str, limit: int = 2):
        self.source_lookups += 1
        return [
            artifact
            for artifact in self.artifacts
            if artifact.workspace_id == workspace_id
            and artifact.metadata.get("source_ref") == source_ref
        ][:limit]


def _artifact(path: Path, source_ref: str, artifact_id: str = "artifact-terminal"):
    return SimpleNamespace(
        id=artifact_id,
        workspace_id="workspace-one",
        storage_ref=str(path),
        metadata={
            "artifact_contract": MOTION_REFERENCE_PROFILE_ARTIFACT_CONTRACT,
            "reference_profile_id": "profile-terminal-v3",
            "source_ref": source_ref,
        },
    )


def _client(module, store: FakeArtifactStore) -> TestClient:
    app = FastAPI()
    app.include_router(module.router, prefix="/api/v1/workspaces")
    app.dependency_overrides[module.get_workspace] = lambda: SimpleNamespace(
        id="workspace-one"
    )
    app.dependency_overrides[
        module.get_motion_reference_profile_artifact_store
    ] = lambda: store
    return TestClient(app)


def test_returns_one_bounded_terminal_profile_summary(tmp_path, monkeypatch) -> None:
    module = _load_route_module()
    source_ref = "https://www.bilibili.com/video/BV13g4y1u7di/"
    monkeypatch.setenv("LOCAL_CORE_DATA_DIR", str(tmp_path))
    path = (
        tmp_path
        / "workspaces/workspace-one/artifacts/yogacoach/reference-profiles/profile.json"
    )
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps(_profile(source_ref)), encoding="utf-8")
    store = FakeArtifactStore([_artifact(path, source_ref)])

    response = _client(module, store).get(
        "/api/v1/workspaces/workspace-one/motion-reference-profiles/selection",
        params={"source_ref": f"{source_ref}?tracking=removed"},
    )

    assert response.status_code == 200
    assert store.source_lookups == 1
    payload = response.json()
    assert payload == {
        "status": "ready",
        "artifact_id": "artifact-terminal",
        "reference_profile_id": "profile-terminal-v3",
        "source_ref": source_ref,
        "chapter_count": 2,
        "duration_ms": 42000,
        "chapters": [
            {
                "chapter_id": "chapter-1",
                "title": "Warm up",
                "start_ms": 0,
                "end_ms": 12000,
                "segment_type": "unknown",
                "confidence": 0.91,
            },
            {
                "chapter_id": "chapter-2",
                "title": "Standing flow",
                "start_ms": 12000,
                "end_ms": 42000,
                "segment_type": "unknown",
                "confidence": 0.94,
            },
        ],
    }
    serialized = json.dumps(payload)
    assert "feature_series" not in serialized
    assert "visual_evidence" not in serialized
    assert "storage_ref" not in serialized


def test_fails_closed_when_terminal_profile_heads_conflict(tmp_path, monkeypatch) -> None:
    module = _load_route_module()
    source_ref = "https://www.bilibili.com/video/BV13g4y1u7di/"
    monkeypatch.setenv("LOCAL_CORE_DATA_DIR", str(tmp_path))
    path = (
        tmp_path
        / "workspaces/workspace-one/artifacts/yogacoach/reference-profiles/profile.json"
    )
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps(_profile(source_ref)), encoding="utf-8")
    store = FakeArtifactStore(
        [
            _artifact(path, source_ref, "artifact-terminal-a"),
            _artifact(path, source_ref, "artifact-terminal-b"),
        ]
    )

    response = _client(module, store).get(
        "/api/v1/workspaces/workspace-one/motion-reference-profiles/selection",
        params={"source_ref": source_ref},
    )

    assert response.status_code == 409
    assert response.json()["detail"] == "motion_reference_profile_source_conflict"
