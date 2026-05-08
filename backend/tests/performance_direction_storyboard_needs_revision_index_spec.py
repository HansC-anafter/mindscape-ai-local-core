from types import SimpleNamespace

import pytest

from backend.app.capabilities.performance_direction.services.object_layer import (
    storyboard_runtime,
)
from backend.app.capabilities.performance_direction.tools.storyboard_patch import (
    _build_storyboard_artifact_summaries,
    _build_storyboard_session_view_from_artifacts,
)


class _Artifact:
    def __init__(self, artifact_id, content_json):
        self.artifact_id = artifact_id
        self.content_json = content_json
        self.created_at = None
        self.updated_at = None
        self.asset_path = None

    def to_dict(self):
        return {
            "artifact_id": self.artifact_id,
            "content": self.content_json,
        }


def _canonical_artifact():
    return _Artifact(
        "storyboard-canonical",
        {
            "branch_kind": "canonical",
            "editorial_status": "accepted",
            "storyboard": {
                "storyboard_id": "sb-1",
                "scenes": [
                    {
                        "scene_id": "sc01",
                        "title": "Opening scene",
                        "visual_prompt": "Open on the product proof point.",
                        "reference_ids": ["ref_a"],
                    }
                ],
            },
        },
    )


def _needs_revision_proposal():
    return _Artifact(
        "proposal-needs-revision",
        {
            "branch_kind": "proposal",
            "editorial_status": "needs_revision",
            "patched_scene_id": "sc01",
            "proposal_origin": "pd",
            "review_note": "Needs a stronger product cue.",
            "storyboard": {
                "storyboard_id": "sb-1",
                "scenes": [{"scene_id": "sc01"}],
            },
        },
    )


def test_storyboard_artifact_summary_counts_needs_revision_as_pending_review_work():
    artifacts = [_canonical_artifact(), _needs_revision_proposal()]

    summaries = _build_storyboard_artifact_summaries(artifacts)
    view = _build_storyboard_session_view_from_artifacts(artifacts)

    proposal_summary = next(
        item for item in summaries if item["artifact_id"] == "proposal-needs-revision"
    )
    assert proposal_summary["editorial_status"] == "needs_revision"
    assert view["pending_proposals"][0]["artifact_id"] == "proposal-needs-revision"
    assert view["proposal_counts"]["needs_revision"] == 1


@pytest.mark.asyncio
async def test_storyboard_object_index_sync_paths_accept_needs_revision(monkeypatch):
    artifacts = [_canonical_artifact(), _needs_revision_proposal()]
    session = SimpleNamespace(
        session_id="pd-session-1",
        workspace_id="workspace-1",
        status="active",
        reference_ids=["ref_a"],
        intent={"summary": "Storyboard review"},
        created_at=None,
        updated_at=None,
    )
    summary = storyboard_runtime._session_index_summary(
        session=session,
        storyboard_artifacts=artifacts,
    )

    async def fake_load_workspace_storyboard_sessions(*, workspace_id, limit):
        assert workspace_id == "workspace-1"
        assert limit == 100
        return [(session, artifacts, summary)]

    monkeypatch.setattr(
        storyboard_runtime,
        "_load_workspace_storyboard_sessions",
        fake_load_workspace_storyboard_sessions,
    )

    aggregate = await storyboard_runtime.sync_storyboard_index(
        workspace_id="workspace-1"
    )
    scenes = await storyboard_runtime.sync_storyboard_scene_index(
        workspace_id="workspace-1"
    )
    proposals = await storyboard_runtime.sync_storyboard_proposal_index(
        workspace_id="workspace-1"
    )

    assert aggregate["records"][0]["metadata"]["pending_proposal_count"] == 1
    assert aggregate["records"][0]["metadata"]["proposal_counts"]["needs_revision"] == 1
    assert scenes["records"][0]["ref"]["object_kind"] == "storyboard_scene"
    assert proposals["records"][0]["metadata"]["editorial_status"] == "needs_revision"
    assert "needs_revision" in proposals["records"][0]["labels"]
