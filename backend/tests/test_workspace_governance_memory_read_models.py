from types import SimpleNamespace

from workspace_governance_memory_transition_api_test_support import _build_client


def test_workspace_memory_list_returns_filtered_canonical_items(monkeypatch):
    candidate = SimpleNamespace(
        id="mem-1",
        kind="session_episode",
        layer="episodic",
        title="Candidate memory",
        claim="Initial claim",
        summary="Initial summary",
        lifecycle_status="candidate",
        verification_status="observed",
        salience=0.7,
        confidence=0.8,
        subject_type="meeting_session",
        subject_id="sess-1",
        supersedes_memory_id=None,
        observed_at="2026-03-25T00:00:00Z",
        last_confirmed_at=None,
        created_at="2026-03-25T00:00:00Z",
        updated_at="2026-03-25T00:00:00Z",
    )
    active = SimpleNamespace(
        id="mem-2",
        kind="principle",
        layer="core",
        title="Verified principle",
        claim="Prefer explicit tradeoffs",
        summary="Use direct architectural tradeoffs",
        lifecycle_status="active",
        verification_status="verified",
        salience=0.9,
        confidence=0.95,
        subject_type="workspace_rule",
        subject_id="rule-1",
        supersedes_memory_id=None,
        observed_at="2026-03-25T01:00:00Z",
        last_confirmed_at="2026-03-25T01:30:00Z",
        created_at="2026-03-25T01:00:00Z",
        updated_at="2026-03-25T01:30:00Z",
    )
    client, _promotion_service, item_store, _meeting_session_store = _build_client(
        monkeypatch,
        item=None,
        items=[candidate, active],
    )

    response = client.get(
        "/api/v1/workspaces/ws-1/governance/memory",
        params=[
            ("lifecycle_status", "active"),
            ("verification_status", "verified"),
            ("limit", "10"),
        ],
    )

    assert response.status_code == 200
    data = response.json()
    assert data["workspace_id"] == "ws-1"
    assert data["total"] == 1
    assert data["items"][0]["id"] == "mem-2"
    assert data["items"][0]["lifecycle_status"] == "active"
    assert data["items"][0]["verification_status"] == "verified"
    assert item_store.list_calls == [
        {
            "context_type": "workspace",
            "context_id": "ws-1",
            "layer": None,
            "kind": None,
            "lifecycle_statuses": ["active"],
            "verification_statuses": ["verified"],
            "limit": 10,
        }
    ]


def test_workspace_memory_detail_returns_versions_evidence_and_projections(
    monkeypatch, tmp_path
):
    artifact_dir = tmp_path / "artifacts" / "exec-001"
    artifact_dir.mkdir(parents=True)
    result_json_path = artifact_dir / "result.json"
    summary_md_path = artifact_dir / "summary.md"
    attachment_path = artifact_dir / "attachments" / "artifact.txt"
    attachment_path.parent.mkdir(parents=True)
    result_json_path.write_text('{"status":"ok"}', encoding="utf-8")
    summary_md_path.write_text("# Summary", encoding="utf-8")
    attachment_path.write_text("artifact body", encoding="utf-8")

    trace_dir = tmp_path / ".mindscape" / "traces"
    trace_dir.mkdir(parents=True)
    trace_file_path = trace_dir / "trace-exec-001.json"
    trace_file_path.write_text('{"execution_id":"trace-exec-001"}', encoding="utf-8")

    item = SimpleNamespace(
        id="mem-1",
        context_type="workspace",
        context_id="ws-1",
        kind="session_episode",
        layer="episodic",
        title="Candidate memory",
        claim="Initial claim",
        summary="Initial summary",
        lifecycle_status="active",
        verification_status="verified",
        salience=0.7,
        confidence=0.8,
        subject_type="meeting_session",
        subject_id="sess-1",
        supersedes_memory_id="mem-0",
        observed_at="2026-03-25T00:00:00Z",
        last_confirmed_at="2026-03-25T00:30:00Z",
        created_at="2026-03-25T00:00:00Z",
        updated_at="2026-03-25T00:30:00Z",
    )
    version = SimpleNamespace(
        id="ver-1",
        memory_item_id="mem-1",
        version_no=1,
        update_mode="append",
        claim_snapshot="Initial claim",
        summary_snapshot="Initial summary",
        metadata_snapshot={"digest_id": "dig-1"},
        created_at="2026-03-25T00:00:00Z",
        created_from_run_id="run-1",
    )
    evidence = SimpleNamespace(
        id="evi-1",
        memory_item_id="mem-1",
        evidence_type="session_digest",
        evidence_id="dig-1",
        link_role="derived_from",
        excerpt="Digest excerpt",
        confidence=0.9,
        metadata={"source_id": "sess-1"},
        created_at="2026-03-25T00:00:01Z",
    )
    decision_evidence = SimpleNamespace(
        id="evi-2",
        memory_item_id="mem-1",
        evidence_type="meeting_decision",
        evidence_id="decision-1",
        link_role="supports",
        excerpt="Adopt the revised delivery standard.",
        confidence=0.95,
        metadata={"category": "action"},
        created_at="2026-03-25T00:00:02Z",
    )
    artifact_evidence = SimpleNamespace(
        id="evi-3",
        memory_item_id="mem-1",
        evidence_type="artifact_result",
        evidence_id="artifact-1",
        link_role="supports",
        excerpt="Updated artifact reflects the revised delivery standard.",
        confidence=0.96,
        metadata={
            "artifact_type": "draft",
            "landing_artifact_dir": str(artifact_dir),
            "landing_result_json_path": str(result_json_path),
            "landing_summary_md_path": str(summary_md_path),
            "landing_attachments_count": 1,
            "landing_attachments": [str(attachment_path)],
            "landing_landed_at": "2026-03-25T00:00:03Z",
        },
        created_at="2026-03-25T00:00:03Z",
    )
    trace_evidence = SimpleNamespace(
        id="evi-4",
        memory_item_id="mem-1",
        evidence_type="execution_trace",
        evidence_id="trace-exec-001",
        link_role="supports",
        excerpt="Produced a concise landing-page outline and updated the draft files.",
        confidence=0.88,
        metadata={
            "trace_source": "trace_file",
            "trace_file_path": str(trace_file_path),
            "sandbox_path": str(tmp_path),
            "tool_call_count": 2,
            "file_change_count": 2,
            "files_created_count": 1,
            "files_modified_count": 1,
            "success": True,
            "duration_seconds": 12.5,
            "task_description": "Generate a concise landing-page outline.",
            "output_summary": (
                "Produced a concise landing-page outline and updated the draft files."
            ),
        },
        created_at="2026-03-25T00:00:03Z",
    )
    receipt_evidence = SimpleNamespace(
        id="evi-5",
        memory_item_id="mem-1",
        evidence_type="writeback_receipt",
        evidence_id="receipt-1",
        link_role="derived_from",
        excerpt="Projection receipt",
        confidence=1.0,
        metadata={"target_table": "personal_knowledge"},
        created_at="2026-03-25T00:00:04Z",
    )
    edge = SimpleNamespace(
        id="edge-1",
        from_memory_id="mem-1",
        to_memory_id="mem-2",
        edge_type="supersedes",
        weight=None,
        valid_from="2026-03-25T01:00:00Z",
        valid_to=None,
        evidence_strength=1.0,
        metadata={"reason": "newer evidence"},
        created_at="2026-03-25T01:00:00Z",
    )
    knowledge = SimpleNamespace(
        id="pk-1",
        knowledge_type="principle",
        content="Prefer explicit tradeoffs",
        status="verified",
        confidence=0.92,
        created_at="2026-03-25T00:01:00Z",
        last_verified_at="2026-03-25T00:30:00Z",
        metadata={"canonical_projection": {"source_memory_item_id": "mem-1"}},
    )
    goal = SimpleNamespace(
        id="goal-1",
        title="Finish phase 1",
        description="Close the loop",
        status="active",
        horizon="quarter",
        created_at="2026-03-25T00:02:00Z",
        confirmed_at="2026-03-25T00:30:00Z",
        metadata={"canonical_projection": {"source_memory_item_id": "mem-1"}},
    )
    client, _promotion_service, _item_store, _meeting_session_store = _build_client(
        monkeypatch,
        item=item,
        versions=[version],
        evidence_links=[
            evidence,
            decision_evidence,
            artifact_evidence,
            trace_evidence,
            receipt_evidence,
        ],
        edges=[edge],
        knowledge_entries=[knowledge],
        goal_entries=[goal],
    )

    response = client.get("/api/v1/workspaces/ws-1/governance/memory/mem-1")

    assert response.status_code == 200
    data = response.json()
    assert data["workspace_id"] == "ws-1"
    assert data["memory_item"]["id"] == "mem-1"
    assert data["memory_item"]["supersedes_memory_id"] == "mem-0"
    assert data["versions"][0]["id"] == "ver-1"
    assert data["versions"][0]["metadata_snapshot"]["digest_id"] == "dig-1"
    assert data["evidence"][0]["id"] == "evi-1"
    assert data["evidence"][0]["link_role"] == "derived_from"
    assert data["outgoing_edges"][0]["id"] == "edge-1"
    assert data["outgoing_edges"][0]["edge_type"] == "supersedes"
    assert data["personal_knowledge_projections"][0]["id"] == "pk-1"
    assert data["goal_projections"][0]["id"] == "goal-1"
    assert data["evidence_coverage"] == {
        "deliberation": 2,
        "execution": 2,
        "governance": 1,
        "support": 3,
        "derived": 2,
    }
    assert data["evidence"][2]["artifact_landing"] == {
        "artifact_dir": str(artifact_dir),
        "result_json_path": str(result_json_path),
        "summary_md_path": str(summary_md_path),
        "attachments_count": 1,
        "attachments": [str(attachment_path)],
        "landed_at": "2026-03-25T00:00:03Z",
        "artifact_dir_exists": True,
        "result_json_exists": True,
        "summary_md_exists": True,
    }
    assert data["evidence"][3]["execution_trace_drilldown"] == {
        "trace_source": "trace_file",
        "trace_file_path": str(trace_file_path),
        "trace_file_exists": True,
        "sandbox_path": str(tmp_path),
        "tool_call_count": 2,
        "file_change_count": 2,
        "files_created_count": 1,
        "files_modified_count": 1,
        "success": True,
        "duration_seconds": 12.5,
        "task_description": "Generate a concise landing-page outline.",
        "output_summary": (
            "Produced a concise landing-page outline and updated the draft files."
        ),
    }
    assert data["transition_cues"][0]["id"] == "stale-usage"
    assert any(cue["id"] == "supersede-usage" for cue in data["transition_cues"])
    assert data["successor_draft_suggestion"] == {
        "title": "Candidate memory Revision",
        "claim": "Updated artifact reflects the revised delivery standard.",
        "summary": (
            "Successor drafted from artifact result. Coverage: 2 deliberation, "
            "2 execution, 1 governance. Anchor evidence: artifact-1."
        ),
        "primary_evidence_id": "artifact-1",
        "primary_evidence_type": "artifact_result",
    }
    assert (
        data["transition_reason_suggestions"]["verify"]
        == "Verified after reviewing Artifact Result artifact-1 with 2 deliberation signals and 3 downstream execution or governance signals."
    )
    assert (
        data["transition_reason_suggestions"]["stale"]
        == "Marked stale because the active workspace context moved beyond this claim and no replacement was finalized from Artifact Result artifact-1."
    )
    assert (
        data["transition_reason_suggestions"]["supersede"]
        == "Superseded after Artifact Result artifact-1 established a newer operating claim for Candidate memory."
    )
