from meeting_memory_writeback_orchestrator_test_support import (
    Artifact,
    ArtifactType,
    FakeArtifactStore,
    FakeEvidenceLinkStore,
    FakeGovernanceStore,
    FakeIntentLogStore,
    FakeLegacyProjectionAdapter,
    FakeLensPatchStore,
    FakeMeetingSessionStore,
    FakeMetadataProjectionAdapter,
    FakeSession,
    FakeWritebackReceiptStore,
    IntentLog,
    LensPatch,
    MeetingDecision,
    PatchStatus,
    PrimaryActionType,
    WritebackReceipt,
    _utc_now,
    build_orchestrator,
)


class TestMeetingMemoryWritebackOrchestratorGovernance:
    def test_first_run_attaches_intent_log_evidence_for_session_window(self):
        adapter = FakeLegacyProjectionAdapter()
        metadata_adapter = FakeMetadataProjectionAdapter()
        evidence_store = FakeEvidenceLinkStore()
        session = FakeSession()
        intent_log = IntentLog(
            id="intent-log-001",
            timestamp=session.ended_at,
            raw_input="Help me draft the outline for the landing page.",
            channel="api",
            profile_id="profile-001",
            project_id="proj-001",
            workspace_id="ws-001",
            pipeline_steps={},
            final_decision={
                "selected_playbook_code": "outline_pack",
                "resolution_strategy": "direct_match",
                "requires_user_approval": True,
            },
            user_override={"selected_playbook_code": "outline_pack"},
            metadata={},
        )
        orchestrator = build_orchestrator(
            evidence_link_store=evidence_store,
            intent_log_store=FakeIntentLogStore([intent_log]),
            legacy_projection_adapter=adapter,
            metadata_projection_adapter=metadata_adapter,
        )

        result = orchestrator.run_for_closed_session(
            session=session,
            workspace=object(),
            profile_id="profile-001",
        )

        assert result["run"].summary["intent_log_count"] == 1
        assert result["run"].summary["intent_log_links_created"] == 1
        intent_links = [
            link for link in evidence_store.links if link.evidence_type == "intent_log"
        ]
        assert len(intent_links) == 1
        assert intent_links[0].evidence_id == "intent-log-001"
        assert intent_links[0].metadata["selected_playbook_code"] == "outline_pack"
        assert intent_links[0].metadata["requires_user_approval"] is True
        assert intent_links[0].metadata["has_user_override"] is True
        assert (
            intent_links[0].excerpt
            == "Selected outline_pack. Resolution direct_match. User approval required. User override recorded."
        )

    def test_first_run_attaches_governance_decision_evidence_from_execution(self):
        adapter = FakeLegacyProjectionAdapter()
        metadata_adapter = FakeMetadataProjectionAdapter()
        decision = MeetingDecision(
            id="decision-002c",
            session_id="sess-001",
            workspace_id="ws-001",
            category="action",
            content="Review whether the generated outline can be approved.",
            status="dispatched",
            source_action_item={"execution_id": "exec-001"},
        )
        evidence_store = FakeEvidenceLinkStore()
        orchestrator = build_orchestrator(
            evidence_link_store=evidence_store,
            meeting_session_store=FakeMeetingSessionStore([decision]),
            governance_store=FakeGovernanceStore(
                {
                    "exec-001": [
                        {
                            "decision_id": "gov-001",
                            "workspace_id": "ws-001",
                            "execution_id": "exec-001",
                            "timestamp": _utc_now().isoformat(),
                            "layer": "policy",
                            "approved": True,
                            "reason": "The draft satisfied workspace guardrails.",
                            "playbook_code": "outline_pack",
                            "metadata": {"requires_review": False},
                        }
                    ]
                }
            ),
            legacy_projection_adapter=adapter,
            metadata_projection_adapter=metadata_adapter,
        )

        result = orchestrator.run_for_closed_session(
            session=FakeSession(),
            workspace=object(),
            profile_id="profile-001",
        )

        assert result["run"].summary["governance_decision_count"] == 1
        assert result["run"].summary["governance_decision_links_created"] == 1
        governance_links = [
            link
            for link in evidence_store.links
            if link.evidence_type == "governance_decision"
        ]
        assert len(governance_links) == 1
        assert governance_links[0].evidence_id == "gov-001"
        assert governance_links[0].metadata["execution_id"] == "exec-001"
        assert governance_links[0].metadata["layer"] == "policy"
        assert governance_links[0].metadata["approved"] is True
        assert (
            governance_links[0].excerpt
            == "Policy approval=True. Playbook outline_pack. The draft satisfied workspace guardrails."
        )

    def test_first_run_attaches_lens_patch_evidence_for_session(self):
        adapter = FakeLegacyProjectionAdapter()
        metadata_adapter = FakeMetadataProjectionAdapter()
        evidence_store = FakeEvidenceLinkStore()
        patch = LensPatch(
            id="lens-patch-001",
            lens_id="lens-001",
            meeting_session_id="sess-001",
            delta={
                "voice.tone": {"before": "neutral", "after": "deliberate"},
                "strategy.mode": {"before": "broad", "after": "focused"},
            },
            evidence_refs=["trace-001", "decision-001"],
            confidence=0.84,
            status=PatchStatus.APPROVED,
            lens_version_before=3,
            lens_version_after=4,
        )
        orchestrator = build_orchestrator(
            evidence_link_store=evidence_store,
            lens_patch_store=FakeLensPatchStore([patch]),
            legacy_projection_adapter=adapter,
            metadata_projection_adapter=metadata_adapter,
        )

        result = orchestrator.run_for_closed_session(
            session=FakeSession(),
            workspace=object(),
            profile_id="profile-001",
        )

        assert result["run"].summary["lens_patch_count"] == 1
        assert result["run"].summary["lens_patch_links_created"] == 1
        lens_patch_links = [
            link for link in evidence_store.links if link.evidence_type == "lens_patch"
        ]
        assert len(lens_patch_links) == 1
        assert lens_patch_links[0].evidence_id == "lens-patch-001"
        assert lens_patch_links[0].metadata["lens_id"] == "lens-001"
        assert lens_patch_links[0].metadata["status"] == "approved"
        assert lens_patch_links[0].metadata["delta_magnitude"] == 2
        assert lens_patch_links[0].metadata["evidence_ref_count"] == 2
        assert (
            lens_patch_links[0].excerpt
            == "Lens patch approved. Changed voice.tone, strategy.mode. Confidence 0.84."
        )

    def test_first_run_attaches_artifact_result_evidence_from_meeting_decision(self):
        adapter = FakeLegacyProjectionAdapter()
        metadata_adapter = FakeMetadataProjectionAdapter()
        decision = MeetingDecision(
            id="decision-003",
            session_id="sess-001",
            workspace_id="ws-001",
            category="action",
            content="Review the generated artifact from the execution.",
            status="dispatched",
            source_action_item={"execution_id": "exec-002"},
        )
        evidence_store = FakeEvidenceLinkStore()
        orchestrator = build_orchestrator(
            evidence_link_store=evidence_store,
            meeting_session_store=FakeMeetingSessionStore([decision]),
            artifact_store=FakeArtifactStore(
                {
                    "exec-002": Artifact(
                        id="artifact-001",
                        workspace_id="ws-001",
                        task_id="task-002",
                        execution_id="exec-002",
                        playbook_code="outline_pack",
                        artifact_type=ArtifactType.DRAFT,
                        title="Outline Draft",
                        summary="Generated an outline artifact with introduction, argument, and closing sections.",
                        primary_action_type=PrimaryActionType.PREVIEW,
                        metadata={
                            "landing": {
                                "artifact_dir": "/tmp/ws-001/artifacts/exec-002",
                                "result_json_path": "/tmp/ws-001/artifacts/exec-002/result.json",
                                "summary_md_path": "/tmp/ws-001/artifacts/exec-002/summary.md",
                                "attachments_count": 2,
                                "attachments": [
                                    "/tmp/ws-001/artifacts/exec-002/attachments/draft.md",
                                    "/tmp/ws-001/artifacts/exec-002/attachments/notes.md",
                                ],
                                "landed_at": "2026-03-25T00:00:00Z",
                            }
                        },
                    )
                }
            ),
            legacy_projection_adapter=adapter,
            metadata_projection_adapter=metadata_adapter,
        )

        result = orchestrator.run_for_closed_session(
            session=FakeSession(),
            workspace=object(),
            profile_id="profile-001",
        )

        assert result["run"].summary["artifact_result_count"] == 1
        assert result["run"].summary["artifact_result_links_created"] == 1
        artifact_links = [
            link for link in evidence_store.links if link.evidence_type == "artifact_result"
        ]
        assert len(artifact_links) == 1
        assert artifact_links[0].evidence_id == "artifact-001"
        assert artifact_links[0].metadata["execution_id"] == "exec-002"
        assert artifact_links[0].metadata["playbook_code"] == "outline_pack"
        assert (
            artifact_links[0].metadata["landing_artifact_dir"]
            == "/tmp/ws-001/artifacts/exec-002"
        )
        assert (
            artifact_links[0].metadata["landing_result_json_path"]
            == "/tmp/ws-001/artifacts/exec-002/result.json"
        )
        assert artifact_links[0].metadata["landing_attachments_count"] == 2
        assert artifact_links[0].metadata["landing_attachments"] == [
            "/tmp/ws-001/artifacts/exec-002/attachments/draft.md",
            "/tmp/ws-001/artifacts/exec-002/attachments/notes.md",
        ]
        assert artifact_links[0].metadata["landing_landed_at"] == "2026-03-25T00:00:00Z"
        assert (
            artifact_links[0].excerpt
            == "Generated an outline artifact with introduction, argument, and closing sections."
        )

    def test_first_run_attaches_writeback_receipt_evidence(self):
        adapter = FakeLegacyProjectionAdapter()
        metadata_adapter = FakeMetadataProjectionAdapter()
        evidence_store = FakeEvidenceLinkStore()
        receipt_store = FakeWritebackReceiptStore(
            resolver=lambda source_memory_item_id: [
                WritebackReceipt(
                    id="receipt-001",
                    meta_session_id="sess-001",
                    source_decision_id="digest-001",
                    target_table="personal_knowledge",
                    target_id="pk-001",
                    writeback_type="candidate",
                    status="completed",
                    metadata={
                        "canonical_projection": {
                            "source_memory_item_id": source_memory_item_id,
                        }
                    },
                )
            ]
        )
        orchestrator = build_orchestrator(
            evidence_link_store=evidence_store,
            writeback_receipt_store=receipt_store,
            legacy_projection_adapter=adapter,
            metadata_projection_adapter=metadata_adapter,
        )

        result = orchestrator.run_for_closed_session(
            session=FakeSession(),
            workspace=object(),
            profile_id="profile-001",
        )

        receipt_links = [
            link
            for link in evidence_store.links
            if link.evidence_type == "writeback_receipt"
        ]
        assert result["run"].summary["writeback_receipt_count"] == 1
        assert result["run"].summary["writeback_receipt_links_created"] == 1
        assert len(receipt_links) == 1
        assert receipt_links[0].evidence_id == "receipt-001"
        assert receipt_links[0].link_role == "derived_from"
        assert receipt_links[0].metadata["target_table"] == "personal_knowledge"
