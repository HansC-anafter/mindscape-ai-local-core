import sys
from pathlib import Path
from types import SimpleNamespace

_BACKEND_ROOT = Path(__file__).resolve().parents[4]
_APP_ROOT = _BACKEND_ROOT / "app"
for _path in (str(_BACKEND_ROOT), str(_APP_ROOT)):
    if _path not in sys.path:
        sys.path.insert(0, _path)

from backend.app.capabilities.spatial_scheduling.services.spatial_schedule_compiler import (
    SPATIAL_SCHEDULE_ARTIFACT_MIME,
    build_spatial_schedule_artifact,
    build_spatial_schedule_context,
    build_spatial_scheduling_ir,
    persist_spatial_schedule_context_to_session,
)
from backend.app.models.handoff import HandoffIn
from backend.app.services.orchestration.meeting._ir_compiler import MeetingIRCompilerMixin


class _FakeMeeting(MeetingIRCompilerMixin):
    def __init__(self) -> None:
        self.profile_id = "profile-001"
        self.session = SimpleNamespace(
            id="session-001",
            workspace_id="ws-001",
            project_id="proj-001",
            metadata={
                "governance_context": {"workspace_id": "ws-001", "mode": "director"},
                "memory_packet": {"selection": {"workspace_mode": "director"}},
                "world_memory_packet": {
                    "snapshot_id": "snap-001",
                    "source": "synthetic",
                    "scene_id": "scene.demo",
                    "current_zone": "main_floor",
                },
                "world_card_projection": {
                    "title": "World Card",
                    "summary_lines": ["Scene: scene.demo", "Zone: main_floor"],
                    "constraints": [],
                    "suggested_focus": [],
                    "metadata": {"source": "synthetic"},
                },
                "world_card_text": "World Card\n- Scene: scene.demo\n- Zone: main_floor",
            },
        )


def build_governance_object_schedule():
    return build_spatial_scheduling_ir(
        task_id="task-governance-objects-001",
        workspace_id="ws-001",
        session_id="session-001",
        decision="Counter tray proof lane",
        action_items=[
            {
                "intent_id": "seg-001",
                "title": "切分空間段落並標記作用中物件與錨點",
                "description": "Mark the bounded object and anchor set for the proof lane.",
            },
            {
                "intent_id": "seg-002",
                "title": "產出 world proof lane 可消費的空間排程",
                "description": "Emit the bounded world-proof schedule.",
            },
        ],
        action_intents=None,
        governance={
            "governance_constraints": {
                "spatial_schedule": {
                    "requested": True,
                    "consumer_hints": ["video_renderer", "ue5_runtime"],
                    "bounded_constraints": {
                        "camera": {
                            "entity_ids": ["camera.main"],
                            "must_hold": ["single_viewpoint"],
                        },
                        "objects": [
                            {
                                "entity_id": "object.counter",
                                "role": "support_surface",
                                "label": "Counter",
                            },
                            {
                                "entity_id": "object.tray",
                                "role": "primary_prop",
                                "label": "Tray",
                            },
                        ],
                        "anchors": [
                            {
                                "anchor_id": "anchor.counter",
                                "anchor_kind": "surface",
                                "label": "Counter surface",
                            },
                            {
                                "anchor_id": "anchor.tray_rest",
                                "anchor_kind": "placement",
                                "label": "Tray rest",
                            },
                        ],
                        "spatial_relations": [
                            {
                                "relation": "tray_on_counter",
                                "source_entity_id": "object.tray",
                                "target_anchor_id": "anchor.counter",
                            }
                        ],
                    },
                }
            }
        },
        world_context=None,
    )


def build_native_camera_handoff_schedule_context():
    schedule = build_spatial_scheduling_ir(
        task_id="task-native-camera-001",
        workspace_id="ws-001",
        session_id="session-001",
        decision=(
            "Drive camera.main with hold_then_minor_reframe across anchors "
            "anchor.entry_handoff, anchor.counter, anchor.tray_rest."
        ),
        action_items=[
            {
                "intent_id": "seg-camera-001",
                "title": "Drive camera.main with hold_then_minor_reframe",
                "description": (
                    "Stage the tray handoff from anchor.entry_handoff across "
                    "anchor.counter and settle at anchor.tray_rest."
                ),
            }
        ],
        action_intents=None,
        governance=None,
        world_context=None,
    )
    artifact = build_spatial_schedule_artifact(
        task_id="task-native-camera-001",
        schedule=schedule,
    )
    return schedule, build_spatial_schedule_context(schedule=schedule, artifact=artifact)
