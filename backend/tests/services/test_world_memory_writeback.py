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
                "metadata": {
                    "workspace_mode": "director",
                    "motion_freshness": "missing_provenance",
                    "motion_source_run_id": "run-motion-demo",
                },
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
    assert snapshot["metadata"]["motion_freshness"] == "missing_provenance"
    assert snapshot["metadata"]["motion_source_run_id"] == "run-motion-demo"


def test_world_memory_writeback_persists_performance_state():
    store = _FakeStore()
    orchestrator = WorldMemoryWritebackOrchestrator(store=store)
    workspace = SimpleNamespace(id="ws-performance", metadata={})
    session = SimpleNamespace(
        id="session-performance",
        project_id="proj-performance",
        metadata={
            "world_memory_packet": {
                "snapshot_id": "snap-performance",
                "source": "meeting_governed",
                "scene_id": "scene.performance",
                "current_zone": "preview_stage",
                "performance_state": {
                    "performance_mode": "audio_driven_talking_head",
                    "execution_bridge": "mms_storyboard_preview",
                    "preview_ready_state": "ready",
                    "face_lane_active": True,
                    "face_source_type": "speaker_audio",
                    "body_lane_active": True,
                    "body_source_type": "motion_context",
                    "retarget_ready_state": "ready",
                },
                "metadata": {
                    "performance_freshness": "fresh",
                    "performance_source_run_id": "perf-run-demo",
                    "performance_execution_bridge": "mms_storyboard_preview",
                },
            },
            "world_card_projection": {
                "title": "World Card",
                "summary_lines": [
                    "Scene: scene.performance",
                    "Performance mode: audio_driven_talking_head",
                ],
            },
            "world_card_text": "World Card\n- Scene: scene.performance\n- Performance mode: audio_driven_talking_head",
        },
    )

    result = orchestrator.run_for_closed_session(
        session=session,
        workspace=workspace,
        profile_id="profile-performance",
    )

    snapshot = workspace.metadata["world_memory_core"]["current_root"]["current_snapshot"]

    assert result["updated"] is True
    assert snapshot["performance_state"]["performance_mode"] == (
        "audio_driven_talking_head"
    )
    assert snapshot["performance_state"]["face_source_type"] == "speaker_audio"
    assert snapshot["metadata"]["performance_freshness"] == "fresh"
    assert snapshot["metadata"]["performance_source_run_id"] == "perf-run-demo"
