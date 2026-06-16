from backend.app.services.runtime_dispatch.tokens import (
    build_apply_idempotency_key,
    build_apply_token_digest,
)


def _digest(**overrides):
    payload = {
        "selector": {"selector_type": "explicit_object_refs", "object_refs": ["ref-a"]},
        "target": {"lane_id": "runner:qwen9b"},
        "eligible_task_ids": ["task-a", "task-b"],
        "route_snapshots": [
            {"task_id": "task-a", "queue_shard": "default"},
            {"task_id": "task-b", "queue_shard": "default"},
        ],
        "actor_id": "default_user",
        "workspace_id": "ws-a",
        "created_at": "2026-06-16T00:00:00Z",
        "expires_at": "2026-06-16T00:05:00Z",
    }
    payload.update(overrides)
    return build_apply_token_digest(**payload)


def test_apply_token_digest_is_stable_for_same_payload():
    assert _digest() == _digest()


def test_apply_token_digest_changes_when_actor_workspace_or_route_snapshot_drifts():
    baseline = _digest()

    assert _digest(actor_id="other-user") != baseline
    assert _digest(workspace_id="ws-b") != baseline
    assert _digest(route_snapshots=[{"task_id": "task-a", "queue_shard": "next"}]) != baseline


def test_apply_idempotency_key_is_bound_to_plan_and_token():
    baseline = build_apply_idempotency_key("plan-a", "token-a")

    assert build_apply_idempotency_key("plan-a", "token-a") == baseline
    assert build_apply_idempotency_key("plan-b", "token-a") != baseline
    assert build_apply_idempotency_key("plan-a", "token-b") != baseline
