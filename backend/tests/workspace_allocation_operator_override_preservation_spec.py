from backend.app.services.host_resources.allocation_blueprints import (
    _resolve_blueprint_entry_allocation_payload,
)


def test_blueprint_apply_preserves_authorized_operator_claim_limit() -> None:
    payload = _resolve_blueprint_entry_allocation_payload(
        workspace_id="workspace-1",
        blueprint_id="default-local-host-resources",
        entry={
            "queue_shard": "vision_local",
            "task_family": "ig_reference_vision",
            "label": "Vision Reference Analysis",
            "max_parallel_task_claims": 4,
            "task_selectors": ["ig_analyze_pinned_reference"],
            "blueprint_entry_id": "entry-vision",
        },
        existing_allocation={
            "max_parallel_task_claims": 1,
            "metadata": {
                "operator_override": {
                    "reason": "workspace_vision_local_single_inflight_2026_07_26",
                    "authorized_by": "workspace owner",
                }
            },
        },
    )

    assert payload["max_parallel_task_claims"] == 1
    assert payload["metadata"]["blueprint_max_parallel_task_claims"] == 4
    assert payload["metadata"]["blueprint_apply_preserved_operator_override"] is True
    assert payload["metadata"]["operator_override"]["authorized_by"] == (
        "workspace owner"
    )


def test_blueprint_apply_uses_blueprint_when_no_operator_override_exists() -> None:
    payload = _resolve_blueprint_entry_allocation_payload(
        workspace_id="workspace-1",
        blueprint_id="default-local-host-resources",
        entry={
            "queue_shard": "vision_local",
            "task_family": "ig_reference_vision",
            "max_parallel_task_claims": 4,
        },
        existing_allocation={
            "max_parallel_task_claims": 1,
            "metadata": {"source": "allocation_blueprint"},
        },
    )

    assert payload["max_parallel_task_claims"] == 4
    assert "operator_override" not in payload["metadata"]
