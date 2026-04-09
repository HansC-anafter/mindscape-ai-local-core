from types import SimpleNamespace
from datetime import datetime, timezone

from backend.app.models.meeting_session import MeetingSession, MeetingStatus
from backend.app.services.orchestration.meeting._dispatch_pipeline import stage_finalize
from backend.app.services.orchestration.meeting import program_runtime_adapter


class _FakeSessionStore:
    def __init__(self) -> None:
        self.updated_sessions = []

    def update(self, session: MeetingSession) -> None:
        self.updated_sessions.append(session)


def _make_session() -> MeetingSession:
    session = MeetingSession.new(
        workspace_id="ws-program-run-001",
        project_id="proj-program-run-001",
        thread_id="thread-program-run-001",
        agenda=["Plan a 90-episode season rollout"],
    )
    session.status = MeetingStatus.CLOSED
    session.round_count = 3
    session.action_items = [
        {"title": "Series Bible"},
        {"title": "Storyboard Seeds"},
    ]
    session.metadata = {
        "last_program_spec": {
            "workstreams": [
                {
                    "id": "WS1",
                    "name": "Series Bible",
                    "description": "Draft the season bible.",
                    "eligible_engines": ["playbook:project_breakdown"],
                },
                {
                    "id": "WS2",
                    "name": "Storyboard Seeds",
                    "description": "Draft storyboard seeds.",
                    "eligible_engines": ["tool:storyboard.generate"],
                },
            ],
            "milestones": [
                {
                    "id": "M1",
                    "name": "Arc Gate",
                    "depends_on_streams": ["WS1"],
                    "deliverables": ["series_bible"],
                }
            ],
            "dependency_graph": {"WS2": ["WS1"]},
            "target_outputs": ["series_bible", "storyboard_seed_pack"],
            "scale": "program",
        },
        "last_program_spec_source": "executor_structured",
        "last_program_spec_recorded_at": "2026-04-01T00:00:00+00:00",
    }
    return session


def test_record_session_program_run_persists_summary_and_cursor(monkeypatch):
    session = _make_session()
    session_store = _FakeSessionStore()
    captured = {}

    class FakeProgramRunStore:
        def upsert_for_session(self, program_run):
            captured["program_run"] = program_run
            return program_run

    monkeypatch.setattr(program_runtime_adapter, "ProgramRunStore", FakeProgramRunStore)

    meeting = SimpleNamespace(session=session, session_store=session_store)
    program_run = program_runtime_adapter.record_session_program_run(
        meeting,
        dispatch_result={
            "phase_results": [
                {"phase_id": "WS1", "status": "succeeded"},
                {"phase_id": "WS2", "status": "running"},
            ]
        },
    )

    assert program_run is not None
    assert captured["program_run"].source == "executor_structured"
    assert captured["program_run"].status.value == "open"
    assert captured["program_run"].cursor_state["completed_workstream_ids"] == ["WS1"]
    assert captured["program_run"].cursor_state["remaining_workstream_ids"] == ["WS2"]
    assert session.metadata["program_run_id"] == program_run.id
    assert session.metadata["program_run_summary"]["remaining_work_count"] == 1
    assert session.metadata["program_run_summary"]["completed_work_count"] == 1
    assert session.metadata["program_run_workstream_count"] == 2
    assert session_store.updated_sessions[-1] is session


def test_record_session_program_run_returns_none_without_program_spec(monkeypatch):
    session = MeetingSession.new(
        workspace_id="ws-program-run-001",
        project_id="proj-program-run-001",
        thread_id="thread-program-run-001",
    )
    meeting = SimpleNamespace(session=session, session_store=_FakeSessionStore())

    class ExplodingProgramRunStore:
        def __init__(self):
            raise AssertionError("Store should not be touched without ProgramSpec")

    monkeypatch.setattr(program_runtime_adapter, "ProgramRunStore", ExplodingProgramRunStore)

    assert (
        program_runtime_adapter.record_session_program_run(
            meeting,
            dispatch_result={"phase_results": []},
        )
        is None
    )


def test_stage_finalize_invokes_program_run_recording(monkeypatch):
    session = _make_session()
    recorded = {}

    def fake_record_session_program_run(meeting, *, dispatch_result=None):
        recorded["session_id"] = meeting.session.id
        recorded["dispatch_result"] = dispatch_result
        return None

    monkeypatch.setattr(
        program_runtime_adapter,
        "record_session_program_run",
        fake_record_session_program_run,
    )
    monkeypatch.setattr(
        "backend.app.services.orchestration.meeting._dispatch_pipeline.asyncio.create_task",
        lambda coro: (coro.close(), object())[1],
    )

    meeting = SimpleNamespace(
        session=session,
        session_store=_FakeSessionStore(),
        tasks_store=None,
        _events=[],
        _render_minutes=lambda **kwargs: "minutes",
        _close_session=lambda **kwargs: None,
        _run_l2_bridge_pipeline=lambda: None,
        _emit_minutes_message=lambda minutes_md: None,
    )

    result = stage_finalize(
        meeting,
        meeting_result_cls=lambda **kwargs: kwargs,
        user_message="Plan a season",
        decision="Create a 90-episode rollout",
        critic_notes=[],
        action_items=[],
        converged=True,
        compiled_ir=None,
        dispatch_result={"phase_results": [{"phase_id": "WS1", "status": "succeeded"}]},
    )

    assert recorded["session_id"] == session.id
    assert recorded["dispatch_result"]["phase_results"][0]["phase_id"] == "WS1"
    assert result["session_id"] == session.id


def test_stage_finalize_reconciles_latest_compile_job_for_closed_session(monkeypatch):
    session = _make_session()
    session.status = MeetingStatus.CLOSED
    session.ended_at = datetime.now(timezone.utc)

    captured = {}

    class FakeCompileJob:
        def __init__(self) -> None:
            self.id = "compile-job-001"
            self.status = "running"

    class FakeCompileJobStore:
        def get_latest_for_session(self, session_id):
            captured["session_id"] = session_id
            return FakeCompileJob()

        def mark_succeeded(self, job_id, *, session_id=None, result=None, metadata=None):
            captured["job_id"] = job_id
            captured["result"] = result
            captured["metadata"] = metadata

    monkeypatch.setattr(
        "backend.app.services.orchestration.meeting._dispatch_pipeline.asyncio.create_task",
        lambda coro: (coro.close(), object())[1],
    )

    meeting = SimpleNamespace(
        session=session,
        session_store=_FakeSessionStore(),
        compile_job_store=FakeCompileJobStore(),
        tasks_store=None,
        _events=[],
        _render_minutes=lambda **kwargs: "minutes",
        _close_session=lambda **kwargs: None,
        _run_l2_bridge_pipeline=lambda: None,
        _emit_minutes_message=lambda minutes_md: None,
    )

    stage_finalize(
        meeting,
        meeting_result_cls=lambda **kwargs: kwargs,
        user_message="Plan a season",
        decision="Create a 90-episode rollout",
        critic_notes=[],
        action_items=[{"title": "Series Bible"}],
        converged=True,
        compiled_ir=None,
        dispatch_result={"status": "ok", "phase_results": [{"phase_id": "WS1", "status": "completed"}]},
    )

    assert captured["session_id"] == session.id
    assert captured["job_id"] == "compile-job-001"
    assert captured["result"]["meeting_status"] == "closed"
    assert captured["result"]["action_items_count"] == 1
    assert captured["metadata"]["session_terminal_status"] == "closed"
