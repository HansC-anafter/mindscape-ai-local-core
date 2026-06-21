from types import SimpleNamespace

from workspace_governance_memory_transition_api_test_support import _build_client


def test_workspace_memory_transition_verify_uses_workspace_scoped_memory(monkeypatch):
    item = SimpleNamespace(
        id="mem-1",
        context_type="workspace",
        context_id="ws-1",
    )
    client, promotion_service, _item_store, _meeting_session_store = _build_client(
        monkeypatch,
        item=item,
    )

    response = client.post(
        "/api/v1/workspaces/ws-1/governance/memory/mem-1/transition",
        json={"action": "verify", "reason": "confirmed by user"},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["memory_item_id"] == "mem-1"
    assert data["transition"] == "verify"
    assert data["lifecycle_status"] == "active"
    assert data["verification_status"] == "verified"
    assert data["run_id"] == "run-1"
    assert promotion_service.calls == [
        ("verify", "mem-1", {"reason": "confirmed by user", "idempotency_key": None})
    ]


def test_workspace_memory_transition_rejects_cross_workspace_memory(monkeypatch):
    item = SimpleNamespace(
        id="mem-1",
        context_type="workspace",
        context_id="ws-other",
    )
    client, _promotion_service, _item_store, _meeting_session_store = _build_client(
        monkeypatch,
        item=item,
    )

    response = client.post(
        "/api/v1/workspaces/ws-1/governance/memory/mem-1/transition",
        json={"action": "verify"},
    )

    assert response.status_code == 404
    assert "workspace" in response.json()["detail"]


def test_workspace_memory_transition_supersede_passes_successor_fields(monkeypatch):
    item = SimpleNamespace(
        id="mem-1",
        context_type="workspace",
        context_id="ws-1",
    )
    client, promotion_service, _item_store, _meeting_session_store = _build_client(
        monkeypatch,
        item=item,
    )

    response = client.post(
        "/api/v1/workspaces/ws-1/governance/memory/mem-1/transition",
        json={
            "action": "supersede",
            "reason": "newer evidence",
            "successor_title": "Updated claim",
            "successor_claim": "Updated claim body",
            "successor_summary": "Updated summary",
        },
    )

    assert response.status_code == 200
    data = response.json()
    assert data["transition"] == "supersede"
    assert data["lifecycle_status"] == "superseded"
    assert data["successor_memory_item_id"] == "mem-2"
    assert promotion_service.calls == [
        (
            "supersede",
            "mem-1",
            {
                "successor_memory_item_id": None,
                "successor_title": "Updated claim",
                "successor_claim": "Updated claim body",
                "successor_summary": "Updated summary",
                "reason": "newer evidence",
                "idempotency_key": None,
            },
        )
    ]
