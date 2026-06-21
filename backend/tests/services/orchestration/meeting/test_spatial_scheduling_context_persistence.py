from types import SimpleNamespace

from spatial_scheduling_compiler_test_support import (
    build_spatial_schedule_artifact,
    build_spatial_schedule_context,
    build_spatial_scheduling_ir,
    persist_spatial_schedule_context_to_session,
)


def test_persist_spatial_schedule_context_to_session_merges_same_schedule_receipts():
    session = SimpleNamespace(
        metadata={
            "spatial_schedule_context": {
                "schedule_id": "ssched_same",
                "schema_version": "2026-04-16",
                "artifact_ref": {"artifact_id": "task-old/spatial_schedule"},
                "active_segments": [
                    {
                        "segment_id": "seg_old",
                        "title": "Old segment",
                        "entity_refs": ["actor.old"],
                        "anchor_ids": ["zone.old"],
                    }
                ],
                "constraint_summary": {
                    "consumer_hints": ["performance_direction"],
                    "consumer_prompt_bindings": [
                        {
                            "consumer": "performance_direction",
                            "section_key": "scene",
                            "text": "Preserve the original stage layout.",
                            "anchor_ids": ["zone.old"],
                        }
                    ],
                },
                "consumer_receipts": {
                    "motion_runtime": {
                        "status": "completed",
                        "receipt_ref": {"artifact_id": "motion-receipt-001"},
                    }
                },
                "updated_at": "2026-04-16T10:00:00+00:00",
            }
        }
    )

    persist_spatial_schedule_context_to_session(
        session,
        {
            "schedule_id": "ssched_same",
            "schema_version": "2026-04-16",
            "artifact_ref": {"artifact_id": "task-old/spatial_schedule"},
            "active_segments": [
                {
                    "segment_id": "seg_new",
                    "title": "New segment window",
                    "entity_refs": ["actor.lead"],
                    "anchor_ids": ["zone.stage"],
                }
            ],
            "constraint_summary": {
                "consumer_hints": ["motion_runtime"],
                "consumer_prompt_bindings": [
                    {
                        "consumer": "motion_runtime",
                        "section_key": "camera",
                        "text": "Follow the new stage window segment.",
                        "anchor_ids": ["zone.stage"],
                    }
                ],
            },
            "consumer_receipts": {
                "performance_direction": {
                    "status": "compiled",
                    "receipt_ref": {"artifact_id": "pd-storyboard-001"},
                }
            },
            "updated_at": "2026-04-16T12:00:00+00:00",
        },
    )

    context = session.metadata["spatial_schedule_context"]
    assert context["schedule_id"] == "ssched_same"
    assert context["active_segments"][0]["segment_id"] == "seg_new"
    assert context["consumer_receipts"]["motion_runtime"]["receipt_ref"]["artifact_id"] == (
        "motion-receipt-001"
    )
    assert (
        context["consumer_receipts"]["performance_direction"]["receipt_ref"]["artifact_id"]
        == "pd-storyboard-001"
    )
    assert context["constraint_summary"]["consumer_hints"] == [
        "performance_direction",
        "motion_runtime",
    ]
    assert len(context["constraint_summary"]["consumer_prompt_bindings"]) == 2
    assert context["updated_at"] == "2026-04-16T12:00:00+00:00"


def test_build_spatial_schedule_context_serializes_constraint_summary_items():
    schedule = build_spatial_scheduling_ir(
        task_id="task-serialize-001",
        workspace_id="ws-001",
        session_id="session-001",
        decision="Bounded counter tray execution",
        action_items=[
            {
                "title": "切分空間段落並標記作用中物件與錨點",
                "description": "標記 counter/tray 的 bounded 空間關係。",
            }
        ],
        governance={
            "governance_constraints": {
                "spatial_schedule": {
                    "requested": True,
                    "consumer_hints": ["ue5_runtime"],
                    "bounded_constraints": {
                        "objects": [
                            {"entity_id": "object.counter", "role": "support_surface"},
                            {"entity_id": "object.tray", "role": "primary_prop"},
                        ],
                        "anchors": [
                            {"anchor_id": "anchor.counter", "anchor_kind": "surface"},
                            {"anchor_id": "anchor.tray_rest", "anchor_kind": "placement"},
                        ],
                    },
                }
            }
        },
    )

    artifact = build_spatial_schedule_artifact(
        task_id="task-serialize-001",
        schedule=schedule,
    )
    context = build_spatial_schedule_context(schedule=schedule, artifact=artifact)

    assert context["constraint_summary"]["consumer_hints"] == ["ue5_runtime"]
    assert context["constraint_summary"]["objects"][0]["entity_refs"] == [
        "object.counter"
    ]
    assert context["constraint_summary"]["objects"][1]["entity_refs"] == [
        "object.tray"
    ]
