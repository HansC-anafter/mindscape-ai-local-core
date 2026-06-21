import json

from meeting_memory_writeback_orchestrator_test_support import (
    FakeEvidenceLinkStore,
    FakeLegacyProjectionAdapter,
    FakeMeetingSessionStore,
    FakeMetadataProjectionAdapter,
    FakeSession,
    FakeStageResultsStore,
    FakeTaskStore,
    MeetingDecision,
    Task,
    TaskStatus,
    _utc_now,
    build_orchestrator,
)


class TestMeetingMemoryWritebackOrchestratorDecisions:
    def test_first_run_attaches_meeting_decision_evidence(self):
        adapter = FakeLegacyProjectionAdapter()
        metadata_adapter = FakeMetadataProjectionAdapter()
        decision = MeetingDecision(
            id="decision-001",
            session_id="sess-001",
            workspace_id="ws-001",
            category="action",
            content="Ship the canonical memory writeback before broader retrieval work.",
            status="pending",
        )
        evidence_store = FakeEvidenceLinkStore()
        orchestrator = build_orchestrator(
            evidence_link_store=evidence_store,
            meeting_session_store=FakeMeetingSessionStore([decision]),
            legacy_projection_adapter=adapter,
            metadata_projection_adapter=metadata_adapter,
        )

        result = orchestrator.run_for_closed_session(
            session=FakeSession(),
            workspace=object(),
            profile_id="profile-001",
        )

        assert result["run"].summary["meeting_decision_count"] == 1
        assert result["run"].summary["meeting_decision_links_created"] == 1
        decision_links = [
            link for link in evidence_store.links if link.evidence_type == "meeting_decision"
        ]
        assert len(decision_links) == 1
        assert decision_links[0].evidence_id == "decision-001"
        assert decision_links[0].metadata["category"] == "action"
        assert (
            decision_links[0].excerpt
            == "Ship the canonical memory writeback before broader retrieval work."
        )

    def test_first_run_attaches_task_execution_evidence_from_meeting_decision(self):
        adapter = FakeLegacyProjectionAdapter()
        metadata_adapter = FakeMetadataProjectionAdapter()
        decision = MeetingDecision(
            id="decision-002",
            session_id="sess-001",
            workspace_id="ws-001",
            category="action",
            content="Run the outline generation task and review the result.",
            status="dispatched",
            source_action_item={"execution_id": "exec-001"},
        )
        evidence_store = FakeEvidenceLinkStore()
        orchestrator = build_orchestrator(
            evidence_link_store=evidence_store,
            meeting_session_store=FakeMeetingSessionStore([decision]),
            task_store=FakeTaskStore(
                {
                    "exec-001": Task(
                        id="task-001",
                        workspace_id="ws-001",
                        message_id="msg-001",
                        execution_id="exec-001",
                        pack_id="outline_pack",
                        task_type="generate_outline",
                        status=TaskStatus.SUCCEEDED,
                        result={"summary": "Generated a first-pass outline with three sections."},
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

        assert result["run"].summary["task_execution_count"] == 1
        assert result["run"].summary["task_execution_links_created"] == 1
        task_links = [
            link for link in evidence_store.links if link.evidence_type == "task_execution"
        ]
        assert len(task_links) == 1
        assert task_links[0].evidence_id == "exec-001"
        assert task_links[0].metadata["task_id"] == "task-001"
        assert task_links[0].metadata["pack_id"] == "outline_pack"
        assert (
            task_links[0].excerpt
            == "Generated a first-pass outline with three sections."
        )

    def test_first_run_attaches_execution_trace_evidence_from_task_result(self, tmp_path):
        adapter = FakeLegacyProjectionAdapter()
        metadata_adapter = FakeMetadataProjectionAdapter()
        decision = MeetingDecision(
            id="decision-002a",
            session_id="sess-001",
            workspace_id="ws-001",
            category="action",
            content="Run the external runtime task and capture its trace.",
            status="dispatched",
            source_action_item={"execution_id": "exec-001"},
        )
        evidence_store = FakeEvidenceLinkStore()
        trace_dir = tmp_path / ".mindscape" / "traces"
        trace_dir.mkdir(parents=True, exist_ok=True)
        trace_file = trace_dir / "trace-exec-001.json"
        trace_file.write_text(
            json.dumps(
                {
                    "execution_id": "trace-exec-001",
                    "agent_type": "openclaw",
                    "task_description": "Generate a concise landing-page outline.",
                    "output_summary": "Produced a concise landing-page outline and updated the draft files.",
                    "success": True,
                    "duration_seconds": 12.5,
                    "tool_calls": [
                        {"tool_name": "file_read"},
                        {"tool_name": "file_write"},
                    ],
                    "file_changes": [
                        {"path": "draft.md", "change_type": "created"},
                        {"path": "notes.md", "change_type": "modified"},
                    ],
                    "sandbox_path": str(tmp_path),
                }
            ),
            encoding="utf-8",
        )
        orchestrator = build_orchestrator(
            evidence_link_store=evidence_store,
            meeting_session_store=FakeMeetingSessionStore([decision]),
            task_store=FakeTaskStore(
                {
                    "exec-001": Task(
                        id="task-001a",
                        workspace_id="ws-001",
                        message_id="msg-001a",
                        execution_id="exec-001",
                        pack_id="external_runtime_pack",
                        task_type="workspace_agent_execute",
                        status=TaskStatus.SUCCEEDED,
                        result={
                            "execution_trace": {
                                "execution_id": "trace-exec-001",
                                "trace_id": "trace-001",
                                "agent": "openclaw",
                                "tool_calls": ["file_read", "file_write"],
                                "files_created": ["draft.md"],
                                "files_modified": ["notes.md"],
                                "sandbox_path": str(tmp_path),
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

        assert result["run"].summary["execution_trace_count"] == 1
        assert result["run"].summary["execution_trace_links_created"] == 1
        execution_trace_links = [
            link for link in evidence_store.links if link.evidence_type == "execution_trace"
        ]
        assert len(execution_trace_links) == 1
        assert execution_trace_links[0].evidence_id == "trace-exec-001"
        assert execution_trace_links[0].metadata["agent"] == "openclaw"
        assert execution_trace_links[0].metadata["tool_call_count"] == 2
        assert execution_trace_links[0].metadata["files_created_count"] == 1
        assert execution_trace_links[0].metadata["files_modified_count"] == 1
        assert execution_trace_links[0].metadata["file_change_count"] == 2
        assert execution_trace_links[0].metadata["task_description"] == "Generate a concise landing-page outline."
        assert (
            execution_trace_links[0].metadata["output_summary"]
            == "Produced a concise landing-page outline and updated the draft files."
        )
        assert execution_trace_links[0].metadata["trace_source"] == "trace_file"
        assert (
            execution_trace_links[0].metadata["trace_file_path"]
            == str(trace_dir / "trace-exec-001.json")
        )
        assert execution_trace_links[0].metadata["sandbox_path"] == str(tmp_path)
        assert (
            execution_trace_links[0].excerpt
            == "Produced a concise landing-page outline and updated the draft files."
        )

    def test_first_run_attaches_stage_result_evidence_from_meeting_decision(self):
        adapter = FakeLegacyProjectionAdapter()
        metadata_adapter = FakeMetadataProjectionAdapter()
        decision = MeetingDecision(
            id="decision-002b",
            session_id="sess-001",
            workspace_id="ws-001",
            category="action",
            content="Run the outline generation task and review the draft stage.",
            status="dispatched",
            source_action_item={"execution_id": "exec-001"},
        )
        evidence_store = FakeEvidenceLinkStore()
        from backend.app.services.stores.stage_results_store import StageResult

        stage_result = StageResult(
            id="stage-001",
            execution_id="exec-001",
            step_id="step-001",
            stage_name="final_output",
            result_type="draft",
            content={"summary": "Produced a structured outline draft."},
            preview="Produced a structured outline draft.",
            requires_review=True,
            review_status="pending",
            artifact_id="artifact-001",
            created_at=_utc_now(),
        )
        orchestrator = build_orchestrator(
            evidence_link_store=evidence_store,
            meeting_session_store=FakeMeetingSessionStore([decision]),
            stage_results_store=FakeStageResultsStore({"exec-001": [stage_result]}),
            legacy_projection_adapter=adapter,
            metadata_projection_adapter=metadata_adapter,
        )

        result = orchestrator.run_for_closed_session(
            session=FakeSession(),
            workspace=object(),
            profile_id="profile-001",
        )

        assert result["run"].summary["stage_result_count"] == 1
        assert result["run"].summary["stage_result_links_created"] == 1
        stage_links = [
            link for link in evidence_store.links if link.evidence_type == "stage_result"
        ]
        assert len(stage_links) == 1
        assert stage_links[0].evidence_id == "stage-001"
        assert stage_links[0].metadata["execution_id"] == "exec-001"
        assert stage_links[0].metadata["stage_name"] == "final_output"
        assert stage_links[0].metadata["review_status"] == "pending"
        assert stage_links[0].excerpt == "Produced a structured outline draft."
