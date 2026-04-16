from types import SimpleNamespace

from backend.app.system_capabilities.world_memory_core.services.world_memory_writeback_orchestrator import (
    WorldMemoryWritebackOrchestrator,
)


class _FakeWorkspacesStore:
    def __init__(self) -> None:
        self.updated = []

    def update_workspace_sync(self, workspace):
        self.updated.append(workspace)
        return workspace


class _FakeStore:
    def __init__(self) -> None:
        self.workspaces = _FakeWorkspacesStore()


def test_world_memory_writeback_persists_workspace_state():
    store = _FakeStore()
    orchestrator = WorldMemoryWritebackOrchestrator(store=store)
    workspace = SimpleNamespace(id="ws-001", metadata={})
    session = SimpleNamespace(
        id="session-001",
        project_id="proj-001",
        metadata={
            "world_memory_packet": {
                "snapshot_id": "snap-001",
                "source": "meeting_governed",
                "scene_id": "scene.demo",
                "current_zone": "main_floor",
                "visible_objects": ["camera_a", "host_01"],
                "reachable_zones": ["main_floor", "window_left"],
                "resource_constraints": {"shoot_window_min": 18},
                "environment_state": {"lighting_profile": "warm_morning"},
                "performer_state": {"mode": "host"},
                "geo_anchor": {"place_id": "place-101"},
                "metadata": {"workspace_mode": "director"},
            },
            "world_card_projection": {
                "title": "World Card",
                "summary_lines": ["Scene: scene.demo", "Zone: main_floor"],
            },
            "world_card_text": "World Card\n- Scene: scene.demo\n- Zone: main_floor",
        },
    )

    result = orchestrator.run_for_closed_session(
        session=session,
        workspace=workspace,
        profile_id="profile-001",
    )

    assert result["updated"] is True
    assert result["snapshot_id"] == "snap-001"
    assert workspace.metadata["world_memory_core"]["current_root"]["current_snapshot"][
        "scene_id"
    ] == "scene.demo"
    assert workspace.metadata["world_memory_core"]["latest_delta"]["snapshot_id"] == "snap-001"
    assert workspace.metadata["world_memory_core"]["history_snapshot_ids"] == ["snap-001"]
    assert store.workspaces.updated and store.workspaces.updated[0] is workspace


def test_world_memory_writeback_persists_motion_fields():
    store = _FakeStore()
    orchestrator = WorldMemoryWritebackOrchestrator(store=store)
    workspace = SimpleNamespace(id="ws-motion", metadata={})
    session = SimpleNamespace(
        id="session-motion",
        project_id="proj-motion",
        metadata={
            "world_memory_packet": {
                "snapshot_id": "snap-motion",
                "source": "meeting_governed",
                "scene_id": "scene.motion",
                "current_zone": "preview_stage",
                "active_motion": {
                    "motion_id": "motion-demo",
                    "provider": "comfyui_kimodo",
                    "status": "completed",
                    "fps": 30,
                },
                "motion_artifact_refs": [
                    {
                        "artifact_kind": "motion_fbx",
                        "storage_key": "motion/demo/motion.fbx",
                        "retarget_profile": "ue5_mannequin",
                    }
                ],
                "motion_constraints": {
                    "retarget_profile": "ue5_mannequin",
                    "timing_policy": {"fps": 30},
                },
                "metadata": {"workspace_mode": "director"},
            },
            "world_card_projection": {
                "title": "World Card",
                "summary_lines": [
                    "Scene: scene.motion",
                    "Active motion: motion-demo",
                ],
            },
            "world_card_text": "World Card\n- Scene: scene.motion\n- Active motion: motion-demo",
        },
    )

    result = orchestrator.run_for_closed_session(
        session=session,
        workspace=workspace,
        profile_id="profile-motion",
    )

    snapshot = workspace.metadata["world_memory_core"]["current_root"]["current_snapshot"]

    assert result["updated"] is True
    assert snapshot["active_motion"]["motion_id"] == "motion-demo"
    assert snapshot["motion_artifact_refs"][0]["artifact_kind"] == "motion_fbx"
    assert snapshot["motion_constraints"]["retarget_profile"] == "ue5_mannequin"


def test_world_memory_writeback_persists_spatial_schedule_summary():
    store = _FakeStore()
    orchestrator = WorldMemoryWritebackOrchestrator(store=store)
    workspace = SimpleNamespace(id="ws-schedule", metadata={})
    session = SimpleNamespace(
        id="session-schedule",
        project_id="proj-schedule",
        metadata={
            "world_memory_packet": {
                "snapshot_id": "snap-schedule",
                "source": "meeting_governed",
                "scene_id": "scene.schedule",
                "current_zone": "stage_left",
                "active_schedule": {
                    "schedule_id": "ssched-demo",
                    "status": "planned",
                    "title": "Blocking pass",
                    "segment_count": 2,
                    "entity_kinds": ["actor"],
                },
                "schedule_artifact_refs": [
                    {
                        "artifact_id": "task-demo/artifacts/spatial_schedule",
                        "artifact_type": "application/vnd.mindscape.spatial-scheduling+json",
                        "uri": "task-ir://task-demo/artifacts/spatial_schedule",
                    }
                ],
                "schedule_constraints": {"motion_constraint_count": 1},
                "metadata": {"workspace_mode": "director"},
            },
            "world_card_projection": {
                "title": "World Card",
                "summary_lines": [
                    "Scene: scene.schedule",
                    "Active schedule: Blocking pass [planned] segments=2",
                ],
            },
            "world_card_text": "World Card\n- Scene: scene.schedule\n- Active schedule: Blocking pass [planned] segments=2",
            "spatial_schedule_context": {
                "schedule_id": "ssched-demo",
                "status": "planned",
                "title": "Blocking pass",
                "segment_count": 2,
            },
        },
    )

    result = orchestrator.run_for_closed_session(
        session=session,
        workspace=workspace,
        profile_id="profile-schedule",
    )

    snapshot = workspace.metadata["world_memory_core"]["current_root"]["current_snapshot"]

    assert result["updated"] is True
    assert snapshot["active_schedule"]["schedule_id"] == "ssched-demo"
    assert snapshot["schedule_constraints"]["motion_constraint_count"] == 1
    assert workspace.metadata["spatial_schedule_context"]["schedule_id"] == "ssched-demo"
