import asyncio

from backend.app.models.compile_job import CompileJob
from backend.app.services.stores.compile_job_store import CompileJobStore


def _make_job() -> CompileJob:
    return CompileJob.new(
        workspace_id="ws-stream-001",
        project_id="proj-stream-001",
        thread_id="thread-stream-001",
        profile_id="profile-stream-001",
        session_id="sess-stream-001",
        metadata={
            "entry_point": "compile",
            "_internal_recovery_context": {"handoff_in": {"handoff_id": "secret"}},
        },
    )


def test_build_stream_event_redacts_internal_metadata():
    job = _make_job()
    job.mark_running(
        session_id=job.session_id,
        metadata={"route_kind": "meeting"},
    )

    event = CompileJobStore.build_stream_event(job)

    assert event["type"] == "compile_job_updated"
    assert event["workspace_id"] == "ws-stream-001"
    assert event["project_id"] == "proj-stream-001"
    assert event["thread_id"] == "thread-stream-001"
    assert event["payload"]["compile_job_id"] == job.id
    assert event["payload"]["session_id"] == "sess-stream-001"
    assert event["payload"]["status"] == "running"
    assert event["payload"]["terminal"] is False
    assert event["payload"]["metadata"] == {
        "entry_point": "compile",
        "route_kind": "meeting",
    }
    assert "_internal_recovery_context" not in event["payload"]["metadata"]


def test_emit_stream_event_schedules_workspace_publish(monkeypatch):
    job = _make_job()
    job.mark_succeeded(
        session_id=job.session_id,
        result={"status": "compiled"},
        metadata={"handoff_id": "handoff-stream-001"},
    )
    store = object.__new__(CompileJobStore)
    scheduled = {}
    published = {}

    class FakeLoop:
        def create_task(self, coro):
            scheduled["coro"] = coro
            return object()

    async def fake_publish_meeting_chunk(workspace_id, chunk, thread_id):
        published["workspace_id"] = workspace_id
        published["chunk"] = chunk
        published["thread_id"] = thread_id
        return True

    monkeypatch.setattr(
        "backend.app.services.stores.compile_job_store.asyncio.get_running_loop",
        lambda: FakeLoop(),
    )
    monkeypatch.setattr(
        "backend.app.services.cache.async_redis.publish_meeting_chunk",
        fake_publish_meeting_chunk,
    )

    store._emit_stream_event(job)
    assert "coro" in scheduled

    asyncio.run(scheduled["coro"])

    assert published["workspace_id"] == "ws-stream-001"
    assert published["thread_id"] == "thread-stream-001"
    assert published["chunk"]["type"] == "compile_job_updated"
    assert published["chunk"]["payload"]["compile_job_id"] == job.id
    assert published["chunk"]["payload"]["status"] == "succeeded"
    assert published["chunk"]["payload"]["terminal"] is True
    assert published["chunk"]["payload"]["metadata"] == {
        "entry_point": "compile",
        "handoff_id": "handoff-stream-001",
    }
