from types import SimpleNamespace

from backend.app.services.runner_resources import resolve_resource_requirements
from backend.app.services.runner_topology.spec_metadata import (
    _extract_runner_metadata_from_spec,
)


def test_resolves_resource_requirements_by_locked_precedence():
    context = {
        "pack_id": "workspace_planning",
        "inputs": {
            "workspace_id": "ws-1",
            "profile_id": "ig-profile-a",
        },
        "execution_profile": {
            "resource_requirements": {
                "cpu_weight": 6,
                "memory_mb": 768,
                "llm_lane": "analysis",
            },
        },
        "resource_requirements": {
            "browser_contexts": 2,
            "ig_profile_lock": True,
            "expected_duration_class": "long",
        },
    }
    task = SimpleNamespace(
        id="task-1",
        pack_id="workspace_planning",
        execution_context=context,
    )

    requirements = resolve_resource_requirements(
        task,
        execution_context=context,
        playbook_metadata={
            "resource_requirements": {
                "browser_contexts": 1,
                "memory_mb": 512,
                "vision_lane": "ocr",
                "db_write_budget": "high",
            },
        },
        pack_defaults={
            "cpu_weight": 2,
            "memory_mb": 256,
            "db_write_budget": "medium",
        },
    )

    assert requirements.browser_contexts == 2
    assert requirements.ig_profile_lock == "ig-profile-a"
    assert requirements.cpu_weight == 6
    assert requirements.memory_mb == 768
    assert requirements.vision_lane == "ocr"
    assert requirements.llm_lane == "analysis"
    assert requirements.db_write_budget == "high"
    assert requirements.expected_duration_class == "long"


def test_extracts_resource_requirements_from_playbook_execution_profile():
    metadata = _extract_runner_metadata_from_spec(
        {
            "execution_profile": {
                "queue_partition": "browser_local",
                "resource_requirements": {
                    "browser_contexts": 1,
                    "ig_profile_lock": "{profile_id}",
                },
            }
        },
        capability_code="capability-a",
    )

    assert metadata["queue_partition"] == "browser_local"
    assert metadata["resource_requirements"] == {
        "browser_contexts": 1,
        "ig_profile_lock": "{profile_id}",
    }


def test_browser_resource_class_defaults_one_context_and_tracks_memory_source():
    task = SimpleNamespace(
        id="task-browser",
        pack_id="ig_batch_pin_references",
        execution_context={"inputs": {}},
    )

    requirements = resolve_resource_requirements(
        task,
        playbook_metadata={
            "resource_class": "browser",
            "resource_requirements": {"memory_mb": 3584},
        },
    )

    assert requirements.resource_class == "browser"
    assert requirements.browser_contexts == 1
    assert requirements.memory_mb == 3584
    assert requirements.memory_reservation_source == "playbook_profile"


def test_memory_profile_identity_participates_in_resolved_contract():
    task = SimpleNamespace(
        id="task-browser",
        pack_id="ig_batch_pin_references",
        execution_context={"inputs": {}},
    )

    requirements = resolve_resource_requirements(
        task,
        playbook_metadata={
            "resource_class": "browser",
            "resource_requirements": {
                "browser_contexts": 1,
                "memory_profile_id": "ig-browser-calibration-2026-07-10",
            },
        },
    )

    assert (
        requirements.memory_profile_id
        == "ig-browser-calibration-2026-07-10"
    )
    assert requirements.to_dict()["memory_profile_id"] == (
        "ig-browser-calibration-2026-07-10"
    )
