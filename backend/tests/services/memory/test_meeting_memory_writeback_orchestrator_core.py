from meeting_memory_writeback_orchestrator_test_support import (
    FakeDigestStore,
    FakeEvidenceLinkStore,
    FakeLegacyProjectionAdapter,
    FakeLensReceiptStore,
    FakeMemoryItemStore,
    FakeMemoryVersionStore,
    FakeMetadataProjectionAdapter,
    FakeReasoningTraceStore,
    FakeRunStore,
    FakeSession,
    LensReceipt,
    ReasoningGraph,
    ReasoningNode,
    ReasoningTrace,
    build_orchestrator,
)


class TestMeetingMemoryWritebackOrchestratorCore:
    def test_first_run_creates_digest_memory_item_and_evidence(self):
        adapter = FakeLegacyProjectionAdapter()
        metadata_adapter = FakeMetadataProjectionAdapter()
        evidence_store = FakeEvidenceLinkStore()
        orchestrator = build_orchestrator(
            evidence_link_store=evidence_store,
            legacy_projection_adapter=adapter,
            metadata_projection_adapter=metadata_adapter,
        )

        result = orchestrator.run_for_closed_session(
            session=FakeSession(),
            workspace=object(),
            profile_id="profile-001",
        )

        assert result["created"] is True
        assert result["digest"] is not None
        assert result["memory_item"] is not None
        assert result["run"].status == "completed"
        assert result["run"].summary["legacy_extraction_triggered"] is True
        assert result["run"].summary["legacy_metadata_projection_triggered"] is True
        assert len(adapter.calls) == 1
        assert len(metadata_adapter.calls) == 1
        assert adapter.calls[0]["source_memory_item_id"] == result["memory_item"].id
        assert adapter.calls[0]["source_writeback_run_id"] == result["run"].id
        assert (
            metadata_adapter.calls[0]["source_memory_item_id"]
            == result["memory_item"].id
        )
        assert (
            metadata_adapter.calls[0]["source_writeback_run_id"] == result["run"].id
        )
        assert result["run"].summary["reasoning_trace_count"] == 0
        assert result["run"].summary["reasoning_trace_links_created"] == 0
        assert result["run"].summary["lens_receipt_count"] == 0
        assert result["run"].summary["lens_receipt_links_created"] == 0
        assert result["run"].summary["meeting_decision_count"] == 0
        assert result["run"].summary["meeting_decision_links_created"] == 0
        assert result["run"].summary["task_execution_count"] == 0
        assert result["run"].summary["task_execution_links_created"] == 0
        assert result["run"].summary["execution_trace_count"] == 0
        assert result["run"].summary["execution_trace_links_created"] == 0
        assert result["run"].summary["artifact_result_count"] == 0
        assert result["run"].summary["artifact_result_links_created"] == 0
        assert result["run"].summary["stage_result_count"] == 0
        assert result["run"].summary["stage_result_links_created"] == 0
        assert result["run"].summary["intent_log_count"] == 0
        assert result["run"].summary["intent_log_links_created"] == 0
        assert result["run"].summary["governance_decision_count"] == 0
        assert result["run"].summary["governance_decision_links_created"] == 0
        assert result["run"].summary["lens_patch_count"] == 0
        assert result["run"].summary["lens_patch_links_created"] == 0
        assert result["run"].summary["writeback_receipt_count"] == 0
        assert result["run"].summary["writeback_receipt_links_created"] == 0

    def test_completed_run_is_idempotent(self):
        adapter = FakeLegacyProjectionAdapter()
        metadata_adapter = FakeMetadataProjectionAdapter()
        run_store = FakeRunStore()
        digest_store = FakeDigestStore()
        item_store = FakeMemoryItemStore()
        version_store = FakeMemoryVersionStore()
        evidence_store = FakeEvidenceLinkStore()

        orchestrator = build_orchestrator(
            run_store=run_store,
            digest_store=digest_store,
            memory_item_store=item_store,
            memory_version_store=version_store,
            evidence_link_store=evidence_store,
            legacy_projection_adapter=adapter,
            metadata_projection_adapter=metadata_adapter,
        )

        first = orchestrator.run_for_closed_session(
            session=FakeSession(),
            workspace=object(),
            profile_id="profile-001",
        )
        second = orchestrator.run_for_closed_session(
            session=FakeSession(),
            workspace=object(),
            profile_id="profile-001",
        )

        assert first["run"].id == second["run"].id
        assert len(digest_store.created) == 1
        assert len(item_store.created) == 1
        assert len(version_store.created) == 1
        assert len(evidence_store.links) == 1
        assert len(adapter.calls) == 1
        assert len(metadata_adapter.calls) == 1
        assert second["created"] is False

    def test_first_run_attaches_reasoning_trace_evidence(self):
        adapter = FakeLegacyProjectionAdapter()
        metadata_adapter = FakeMetadataProjectionAdapter()
        trace = ReasoningTrace.new(
            workspace_id="ws-001",
            graph=ReasoningGraph(
                nodes=[
                    ReasoningNode(
                        id="n1",
                        content="The draft should keep direct tradeoff framing.",
                        type="conclusion",
                    )
                ],
                edges=[],
                answer="Keep the architectural tradeoff framing explicit.",
            ),
            meeting_session_id="sess-001",
            execution_id="exec-001",
        )
        evidence_store = FakeEvidenceLinkStore()
        orchestrator = build_orchestrator(
            evidence_link_store=evidence_store,
            reasoning_trace_store=FakeReasoningTraceStore([trace]),
            legacy_projection_adapter=adapter,
            metadata_projection_adapter=metadata_adapter,
        )

        result = orchestrator.run_for_closed_session(
            session=FakeSession(),
            workspace=object(),
            profile_id="profile-001",
        )

        assert result["run"].summary["reasoning_trace_count"] == 1
        assert result["run"].summary["reasoning_trace_links_created"] == 1
        assert len(evidence_store.links) == 2
        reasoning_links = [
            link for link in evidence_store.links if link.evidence_type == "reasoning_trace"
        ]
        assert len(reasoning_links) == 1
        assert reasoning_links[0].evidence_id == trace.id
        assert reasoning_links[0].link_role == "supports"
        assert reasoning_links[0].metadata["execution_id"] == "exec-001"
        assert reasoning_links[0].excerpt == "Keep the architectural tradeoff framing explicit."

    def test_first_run_attaches_lens_receipt_evidence(self):
        adapter = FakeLegacyProjectionAdapter()
        metadata_adapter = FakeMetadataProjectionAdapter()
        trace = ReasoningTrace.new(
            workspace_id="ws-001",
            graph=ReasoningGraph(
                nodes=[
                    ReasoningNode(
                        id="n1",
                        content="Keep the tone deliberate.",
                        type="conclusion",
                    )
                ],
                edges=[],
            ),
            meeting_session_id="sess-001",
            execution_id="exec-001",
        )
        evidence_store = FakeEvidenceLinkStore()
        orchestrator = build_orchestrator(
            evidence_link_store=evidence_store,
            reasoning_trace_store=FakeReasoningTraceStore([trace]),
            lens_receipt_store=FakeLensReceiptStore(
                {
                    "exec-001": LensReceipt(
                        id="lens-receipt-001",
                        execution_id="exec-001",
                        workspace_id="ws-001",
                        effective_lens_hash="lens-hash-001",
                        diff_summary="The lens tightened tone and kept the answer concise.",
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

        assert result["run"].summary["lens_receipt_count"] == 1
        assert result["run"].summary["lens_receipt_links_created"] == 1
        lens_links = [
            link for link in evidence_store.links if link.evidence_type == "lens_receipt"
        ]
        assert len(lens_links) == 1
        assert lens_links[0].evidence_id == "lens-receipt-001"
        assert lens_links[0].metadata["execution_id"] == "exec-001"
        assert (
            lens_links[0].excerpt
            == "The lens tightened tone and kept the answer concise."
        )
