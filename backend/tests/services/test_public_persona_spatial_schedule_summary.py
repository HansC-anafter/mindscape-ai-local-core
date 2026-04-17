from backend.app.capabilities.public_persona_studio.services.spatial_schedule_summary import (
    SPATIAL_SCHEDULE_ARTIFACT_MIME,
    resolve_spatial_schedule_artifact_ref,
    resolve_spatial_schedule_summary,
)


def test_resolve_spatial_schedule_summary_merges_workspace_and_session_receipts():
    workspace_metadata = {
        "spatial_schedule_context": {
            "schedule_id": "ssched_demo",
            "status": "planned",
            "artifact_ref": {
                "artifact_id": "task-workspace/spatial_schedule",
                "type": SPATIAL_SCHEDULE_ARTIFACT_MIME,
            },
            "active_segments": [
                {
                    "segment_id": "seg_workspace",
                    "title": "Workspace segment",
                    "entity_refs": ["actor:lead"],
                    "anchor_ids": ["anchor_stage"],
                }
            ],
            "consumer_receipts": {
                "motion_runtime": {
                    "status": "ready",
                    "receipt_ref": {"artifact_id": "motion/workspace"},
                }
            },
            "updated_at": "2026-04-17T10:00:00+00:00",
        }
    }
    meeting_session_payload = {
        "metadata": {
            "spatial_schedule_context": {
                "schedule_id": "ssched_demo",
                "status": "compiled",
                "artifact_ref": {
                    "artifact_id": "task-session/spatial_schedule",
                    "type": SPATIAL_SCHEDULE_ARTIFACT_MIME,
                },
                "active_segments": [
                    {
                        "segment_id": "seg_session",
                        "title": "Session segment",
                        "entity_refs": ["actor:lead", "camera:main"],
                        "anchor_ids": ["anchor_stage"],
                    }
                ],
                "consumer_receipts": {
                    "performance_direction": {
                        "status": "compiled",
                        "receipt_ref": {"artifact_id": "pd/session"},
                    }
                },
                "updated_at": "2026-04-17T12:00:00+00:00",
            }
        }
    }

    summary = resolve_spatial_schedule_summary(
        workspace_metadata=workspace_metadata,
        meeting_session_payload=meeting_session_payload,
    )

    assert summary["schedule_id"] == "ssched_demo"
    assert summary["status"] == "compiled"
    assert summary["artifact_ref"]["artifact_id"] == "task-session/spatial_schedule"
    assert summary["active_segments"][0]["segment_id"] == "seg_session"
    assert (
        summary["consumer_receipts"]["motion_runtime"]["receipt_ref"]["artifact_id"]
        == "motion/workspace"
    )
    assert (
        summary["consumer_receipts"]["performance_direction"]["receipt_ref"][
            "artifact_id"
        ]
        == "pd/session"
    )


def test_resolve_spatial_schedule_summary_converts_workspace_to_revision_on_replan():
    workspace_metadata = {
        "spatial_schedule_context": {
            "schedule_id": "ssched_old",
            "artifact_ref": {
                "artifact_id": "task-workspace/spatial_schedule",
                "type": SPATIAL_SCHEDULE_ARTIFACT_MIME,
            },
            "active_segments": [
                {
                    "segment_id": "seg_old",
                    "title": "Old segment",
                    "entity_refs": ["actor:lead"],
                    "anchor_ids": [],
                }
            ],
            "updated_at": "2026-04-17T09:00:00+00:00",
        }
    }
    meeting_session_payload = {
        "metadata": {
            "spatial_schedule_context": {
                "schedule_id": "ssched_new",
                "artifact_ref": {
                    "artifact_id": "task-session/spatial_schedule",
                    "type": SPATIAL_SCHEDULE_ARTIFACT_MIME,
                },
                "active_segments": [
                    {
                        "segment_id": "seg_new",
                        "title": "New segment",
                        "entity_refs": ["actor:lead", "prop:chair"],
                        "anchor_ids": ["anchor_corner"],
                    }
                ],
                "updated_at": "2026-04-17T12:00:00+00:00",
            }
        }
    }

    summary = resolve_spatial_schedule_summary(
        workspace_metadata=workspace_metadata,
        meeting_session_payload=meeting_session_payload,
    )

    assert summary["schedule_id"] == "ssched_new"
    assert summary["artifact_ref"]["artifact_id"] == "task-session/spatial_schedule"
    assert summary["schedule_revision_refs"] == [
        {
            "schedule_id": "ssched_old",
            "artifact_ref": {
                "artifact_id": "task-workspace/spatial_schedule",
                "type": SPATIAL_SCHEDULE_ARTIFACT_MIME,
            },
            "updated_at": "2026-04-17T09:00:00+00:00",
            "relation": "supersedes",
        }
    ]


def test_resolve_spatial_schedule_artifact_ref_upgrades_legacy_summary():
    artifact_ref = resolve_spatial_schedule_artifact_ref(
        {
            "schedule_id": "ssched_legacy",
            "source_artifact_id": "task-legacy/spatial_schedule",
            "artifact_type": SPATIAL_SCHEDULE_ARTIFACT_MIME,
            "active_segment_ids": ["seg_legacy"],
        }
    )

    assert artifact_ref == {
        "artifact_id": "task-legacy/spatial_schedule",
        "artifact_type": SPATIAL_SCHEDULE_ARTIFACT_MIME,
    }
