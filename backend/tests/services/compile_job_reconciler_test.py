from backend.app.models.compile_job import CompileJob
from backend.app.models.meeting_session import MeetingSession
from backend.app.models.workspace.enums import TaskStatus
from backend.app.services.compile_job_dispatch_manager import CompileJobDispatchManager
from backend.app.services.compile_job_reconciler import CompileJobReconciler
import asyncio


def _make_running_job(session_id: str | None = None) -> CompileJob:
    job = CompileJob.new(
        workspace_id="ws-reconcile-001",
        project_id="proj-reconcile-001",
        thread_id="thread-reconcile-001",
        profile_id="profile-reconcile-001",
        session_id=session_id,
        metadata={
            "entry_point": "compile",
            "_internal_recovery_context": {
                "handoff_in": {
                    "handoff_id": "handoff-reconcile-001",
                    "workspace_id": "ws-reconcile-001",
                    "intent_summary": "resume this compile",
                    "goals": [],
                    "deliverables": [],
                },
                "workspace_id": "ws-reconcile-001",
                "project_id": "proj-reconcile-001",
                "profile_id": "profile-reconcile-001",
                "thread_id": "thread-reconcile-001",
                "source_device_id": "device-reconcile-001",
            },
        },
    )
    job.mark_running(session_id=session_id, metadata={"route_kind": "meeting"})
    return job


def _make_accepted_job(session_id: str | None = None) -> CompileJob:
    return CompileJob.new(
        workspace_id="ws-reconcile-001",
        project_id="proj-reconcile-001",
        thread_id="thread-reconcile-001",
        profile_id="profile-reconcile-001",
        session_id=session_id,
        metadata={
            "entry_point": "compile",
            "_internal_recovery_context": {
                "handoff_in": {
                    "handoff_id": "handoff-reconcile-001",
                    "workspace_id": "ws-reconcile-001",
                    "intent_summary": "resume this compile",
                    "goals": [],
                    "deliverables": [],
                },
                "workspace_id": "ws-reconcile-001",
                "project_id": "proj-reconcile-001",
                "profile_id": "profile-reconcile-001",
                "thread_id": "thread-reconcile-001",
                "source_device_id": "device-reconcile-001",
            },
        },
    )


def _make_active_session() -> MeetingSession:
    session = MeetingSession.new(
        workspace_id="ws-reconcile-001",
        project_id="proj-reconcile-001",
        thread_id="thread-reconcile-001",
    )
    session.start()
    return session


class FakeCompileJobStore:
    def __init__(self, jobs):
        self.jobs = list(jobs)
        self.mark_succeeded_calls = []
        self.mark_failed_calls = []
        self.claim_calls = []
        self.requeue_calls = []

    def list_incomplete(self, *, limit=200):
        return self.jobs[:limit]

    def list_accepted(self, *, limit=200):
        accepted_jobs = [
            job
            for job in self.jobs
            if (job.status.value if hasattr(job.status, "value") else job.status)
            == "accepted"
        ]
        return accepted_jobs[:limit]

    def try_claim_for_resume(self, job_id, *, session_id=None, metadata=None):
        self.claim_calls.append(
            {
                "job_id": job_id,
                "session_id": session_id,
                "metadata": metadata,
            }
        )
        for job in self.jobs:
            if job.id == job_id and (
                job.status.value if hasattr(job.status, "value") else job.status
            ) == "accepted":
                job.mark_running(session_id=session_id, metadata=metadata)
                return job
        return None

    def mark_succeeded(self, job_id, *, session_id=None, result=None, metadata=None):
        self.mark_succeeded_calls.append(
            {
                "job_id": job_id,
                "session_id": session_id,
                "result": result,
                "metadata": metadata,
            }
        )

    def mark_failed(self, job_id, error, *, session_id=None, metadata=None):
        self.mark_failed_calls.append(
            {
                "job_id": job_id,
                "error": error,
                "session_id": session_id,
                "metadata": metadata,
            }
        )

    def get_by_id(self, job_id):
        for job in self.jobs:
            if job.id == job_id:
                return job
        return None

    def requeue_for_resume(self, job_id, *, session_id=None, metadata=None):
        self.requeue_calls.append(
            {
                "job_id": job_id,
                "session_id": session_id,
                "metadata": metadata,
            }
        )
        job = self.get_by_id(job_id)
        if not job:
            return None
        status = job.status.value if hasattr(job.status, "value") else job.status
        if status != "running":
            return None
        job.status = job.status.__class__("accepted")
        job.session_id = session_id or job.session_id
        job.error = None
        job.completed_at = None
        job.started_at = None
        if metadata:
            job.metadata.update(metadata)
        return job


class FakeMeetingSessionStore:
    def __init__(self, sessions):
        self.sessions = dict(sessions)
        self.updated_sessions = []

    def get_by_id(self, session_id):
        return self.sessions.get(session_id)

    def update(self, session):
        self.sessions[session.id] = session
        self.updated_sessions.append(session)


class FakeTask:
    def __init__(self, meeting_session_id, status):
        self.meeting_session_id = meeting_session_id
        self.status = status


class FakeTasksStore:
    def __init__(self, tasks=None):
        self.tasks = list(tasks or [])

    def list_tasks_by_meeting_session(self, session_id):
        return [task for task in self.tasks if task.meeting_session_id == session_id]


def test_reconcile_startup_orphans_marks_closed_session_job_succeeded():
    session = _make_active_session()
    session.action_items = [{"description": "ship"}]
    session.close()
    job = _make_running_job(session.id)
    compile_job_store = FakeCompileJobStore([job])
    meeting_session_store = FakeMeetingSessionStore({session.id: session})
    tasks_store = FakeTasksStore([FakeTask(session.id, TaskStatus.SUCCEEDED)])

    reconciler = CompileJobReconciler(
        compile_job_store=compile_job_store,
        meeting_session_store=meeting_session_store,
        tasks_store=tasks_store,
    )
    summary = reconciler.reconcile_startup_orphans()

    assert summary == {
        "inspected": 1,
        "succeeded": 1,
        "failed": 0,
        "session_failed": 0,
    }
    assert compile_job_store.mark_failed_calls == []
    assert compile_job_store.mark_succeeded_calls == [
        {
            "job_id": job.id,
            "session_id": session.id,
            "result": {
                "status": "compiled",
                "session_id": session.id,
                "task_ir_id": None,
                "persisted": False,
                "action_items_count": 1,
                "reconciled_from_session": True,
            },
            "metadata": {
                "recovery_reason": "startup_orphan_reconcile",
                "reconciled_from_startup": True,
                "session_status": "closed",
                "session_task_total": 1,
                "session_incomplete_tasks": 0,
                "session_task_statuses": {"succeeded": 1},
            },
        }
    ]


def test_reconcile_startup_orphans_marks_active_session_and_job_failed(monkeypatch):
    session = _make_active_session()
    job = _make_running_job(session.id)
    compile_job_store = FakeCompileJobStore([job])
    meeting_session_store = FakeMeetingSessionStore({session.id: session})
    tasks_store = FakeTasksStore([])
    failure_calls = []

    def fake_mark_compile_session_failed(*, session, error, stage):
        failure_calls.append(
            {
                "session_id": session.id,
                "error": str(error),
                "stage": stage,
            }
        )

    monkeypatch.setattr(
        "backend.app.services.compile_job_reconciler.HandoffBundleService._mark_compile_session_failed",
        fake_mark_compile_session_failed,
    )

    reconciler = CompileJobReconciler(
        compile_job_store=compile_job_store,
        meeting_session_store=meeting_session_store,
        tasks_store=tasks_store,
    )
    summary = reconciler.reconcile_startup_orphans()

    assert summary == {
        "inspected": 1,
        "succeeded": 0,
        "failed": 1,
        "session_failed": 1,
    }
    assert failure_calls == [
        {
            "session_id": session.id,
            "error": (
                "Compile job was interrupted by backend restart before completion "
                f"(session={session.id})."
            ),
            "stage": "startup_recovery",
        }
    ]
    assert compile_job_store.mark_succeeded_calls == []
    assert compile_job_store.mark_failed_calls == [
        {
            "job_id": job.id,
            "error": (
                "Compile job was interrupted by backend restart before completion "
                f"(session={session.id})."
            ),
            "session_id": session.id,
            "metadata": {
                "recovery_reason": "startup_orphan_reconcile",
                "reconciled_from_startup": True,
                "session_status": "active",
                "session_task_total": 0,
                "session_incomplete_tasks": 0,
                "session_task_statuses": {},
            },
        }
    ]


def test_reconcile_startup_orphans_marks_missing_session_job_failed(monkeypatch):
    job = _make_running_job("sess-missing-001")
    compile_job_store = FakeCompileJobStore([job])
    meeting_session_store = FakeMeetingSessionStore({})
    tasks_store = FakeTasksStore([])
    failure_calls = []

    def fake_mark_compile_session_failed(*, session, error, stage):
        failure_calls.append((session, error, stage))

    monkeypatch.setattr(
        "backend.app.services.compile_job_reconciler.HandoffBundleService._mark_compile_session_failed",
        fake_mark_compile_session_failed,
    )

    reconciler = CompileJobReconciler(
        compile_job_store=compile_job_store,
        meeting_session_store=meeting_session_store,
        tasks_store=tasks_store,
    )
    summary = reconciler.reconcile_startup_orphans()

    assert summary == {
        "inspected": 1,
        "succeeded": 0,
        "failed": 1,
        "session_failed": 0,
    }
    assert failure_calls == []
    assert compile_job_store.mark_succeeded_calls == []
    assert compile_job_store.mark_failed_calls == [
        {
            "job_id": job.id,
            "error": (
                "Compile job was interrupted by backend restart before completion."
            ),
            "session_id": None,
            "metadata": {
                "recovery_reason": "startup_orphan_reconcile",
                "reconciled_from_startup": True,
                "session_status": None,
                "session_task_total": 0,
                "session_incomplete_tasks": 0,
                "session_task_statuses": {},
            },
        }
    ]


def test_reconcile_startup_orphans_does_not_mark_success_when_session_tasks_running():
    session = _make_active_session()
    session.action_items = [{"description": "ship"}]
    session.close()
    job = _make_running_job(session.id)
    compile_job_store = FakeCompileJobStore([job])
    meeting_session_store = FakeMeetingSessionStore({session.id: session})
    tasks_store = FakeTasksStore(
        [
            FakeTask(session.id, TaskStatus.SUCCEEDED),
            FakeTask(session.id, TaskStatus.RUNNING),
        ]
    )

    reconciler = CompileJobReconciler(
        compile_job_store=compile_job_store,
        meeting_session_store=meeting_session_store,
        tasks_store=tasks_store,
    )
    summary = reconciler.reconcile_startup_orphans()

    assert summary == {
        "inspected": 1,
        "succeeded": 0,
        "failed": 1,
        "session_failed": 0,
    }
    assert compile_job_store.mark_succeeded_calls == []
    assert compile_job_store.mark_failed_calls == [
        {
            "job_id": job.id,
            "error": "meeting_session_closed_with_nonterminal_tasks",
            "session_id": session.id,
            "metadata": {
                "recovery_reason": "startup_orphan_reconcile",
                "reconciled_from_startup": True,
                "session_status": "closed",
                "session_task_total": 2,
                "session_incomplete_tasks": 1,
                "session_task_statuses": {"succeeded": 1, "running": 1},
            },
        }
    ]


def test_recover_startup_orphans_resumes_accepted_job(monkeypatch):
    session = _make_active_session()
    job = _make_accepted_job(session.id)
    compile_job_store = FakeCompileJobStore([job])
    meeting_session_store = FakeMeetingSessionStore({session.id: session})
    scheduled = {}

    monkeypatch.setattr(
        CompileJobReconciler,
        "_schedule_resume",
        lambda self, job, *, session, recovery_context, failure_stage, claim_metadata: scheduled.update(
            {
                "job_id": job.id,
                "session_id": session.id,
                "recovery_context": recovery_context,
                "failure_stage": failure_stage,
                "claim_metadata": claim_metadata,
            }
        ),
    )

    reconciler = CompileJobReconciler(
        compile_job_store=compile_job_store,
        meeting_session_store=meeting_session_store,
        tasks_store=FakeTasksStore([]),
    )
    summary = asyncio.run(reconciler.recover_startup_orphans())

    assert summary == {
        "inspected": 1,
        "resumed": 1,
        "succeeded": 0,
        "failed": 0,
        "session_failed": 0,
        "skipped": 0,
    }
    assert compile_job_store.claim_calls == [
        {
            "job_id": job.id,
            "session_id": session.id,
            "metadata": {
                "recovery_reason": "startup_resume",
                "recovered_from_startup": True,
            },
        }
    ]
    assert scheduled["job_id"] == job.id
    assert scheduled["session_id"] == session.id
    assert scheduled["recovery_context"]["workspace_id"] == "ws-reconcile-001"
    assert scheduled["failure_stage"] == "startup_resume"
    assert scheduled["claim_metadata"] == {
        "recovery_reason": "startup_resume",
        "recovered_from_startup": True,
    }
    assert compile_job_store.mark_succeeded_calls == []
    assert compile_job_store.mark_failed_calls == []


def test_recover_startup_orphans_resumes_running_job_with_recovery_context(monkeypatch):
    session = _make_active_session()
    session.round_count = 2
    session.metadata["pipeline_stage"] = "deliberation"
    job = _make_running_job(session.id)
    compile_job_store = FakeCompileJobStore([job])
    meeting_session_store = FakeMeetingSessionStore({session.id: session})
    scheduled = {}

    monkeypatch.setattr(
        CompileJobReconciler,
        "_schedule_resume",
        lambda self, job, *, session, recovery_context, failure_stage, claim_metadata: scheduled.update(
            {
                "job_id": job.id,
                "session_id": session.id,
                "recovery_context": recovery_context,
                "failure_stage": failure_stage,
                "claim_metadata": claim_metadata,
            }
        ),
    )

    reconciler = CompileJobReconciler(
        compile_job_store=compile_job_store,
        meeting_session_store=meeting_session_store,
        tasks_store=FakeTasksStore([]),
    )
    summary = asyncio.run(reconciler.recover_startup_orphans())

    assert summary == {
        "inspected": 1,
        "resumed": 1,
        "succeeded": 0,
        "failed": 0,
        "session_failed": 0,
        "skipped": 0,
    }
    assert compile_job_store.requeue_calls == [
        {
            "job_id": job.id,
            "session_id": session.id,
            "metadata": {
                "recovery_reason": "startup_orphan_reconcile",
                "recovered_from_running": True,
            },
        }
    ]
    assert compile_job_store.claim_calls == [
        {
            "job_id": job.id,
            "session_id": session.id,
            "metadata": {
                "recovery_reason": "startup_resume",
                "recovered_from_startup": True,
            },
        }
    ]
    assert scheduled["job_id"] == job.id
    assert scheduled["session_id"] == session.id
    assert scheduled["failure_stage"] == "startup_resume"
    updated_session = meeting_session_store.updated_sessions[-1]
    assert updated_session.status.value == "planned"
    assert updated_session.round_count == 0


def test_dispatch_pending_accepted_jobs_resumes_accepted_job(monkeypatch):
    session = _make_active_session()
    job = _make_accepted_job(session.id)
    compile_job_store = FakeCompileJobStore([job])
    meeting_session_store = FakeMeetingSessionStore({session.id: session})
    scheduled = {}

    monkeypatch.setattr(
        CompileJobReconciler,
        "_schedule_resume",
        lambda self, job, *, session, recovery_context, failure_stage, claim_metadata: scheduled.update(
            {
                "job_id": job.id,
                "session_id": session.id,
                "recovery_context": recovery_context,
                "failure_stage": failure_stage,
                "claim_metadata": claim_metadata,
            }
        ),
    )

    reconciler = CompileJobReconciler(
        compile_job_store=compile_job_store,
        meeting_session_store=meeting_session_store,
        tasks_store=FakeTasksStore([]),
    )
    summary = asyncio.run(reconciler.dispatch_pending_accepted_jobs())

    assert summary == {
        "inspected": 1,
        "resumed": 1,
        "succeeded": 0,
        "failed": 0,
        "session_failed": 0,
        "skipped": 0,
    }
    assert compile_job_store.claim_calls == [
        {
            "job_id": job.id,
            "session_id": session.id,
            "metadata": {
                "dispatch_reason": "runtime_queue_claim",
                "queued_dispatch": True,
            },
        }
    ]
    assert scheduled["job_id"] == job.id
    assert scheduled["session_id"] == session.id
    assert scheduled["failure_stage"] == "queued_dispatch"
    assert scheduled["claim_metadata"] == {
        "dispatch_reason": "runtime_queue_claim",
        "queued_dispatch": True,
    }


def test_requeue_running_jobs_for_shutdown_requeues_active_job():
    session = _make_active_session()
    session.round_count = 2
    session.action_items = [{"description": "stale"}]
    session.minutes_md = "partial"
    session.metadata["pipeline_stage"] = "deliberation"
    job = _make_running_job(session.id)
    compile_job_store = FakeCompileJobStore([job])
    meeting_session_store = FakeMeetingSessionStore({session.id: session})

    reconciler = CompileJobReconciler(
        compile_job_store=compile_job_store,
        meeting_session_store=meeting_session_store,
        tasks_store=FakeTasksStore([]),
    )
    summary = reconciler.requeue_running_jobs_for_shutdown(job_ids=[job.id])

    assert summary == {
        "inspected": 1,
        "requeued": 1,
        "session_reset": 1,
        "skipped": 0,
    }
    assert compile_job_store.requeue_calls == [
        {
            "job_id": job.id,
            "session_id": session.id,
            "metadata": {
                "recovery_reason": "graceful_shutdown_requeue",
                "shutdown_requeued": True,
                "shutdown_requeued_at": compile_job_store.requeue_calls[0][
                    "metadata"
                ]["shutdown_requeued_at"],
            },
        }
    ]
    updated_session = meeting_session_store.updated_sessions[-1]
    assert updated_session.status.value == "planned"
    assert updated_session.round_count == 0
    assert updated_session.action_items == []
    assert updated_session.minutes_md == ""
    assert updated_session.metadata["pipeline_stage_status"] == "interrupted"
    assert updated_session.metadata["shutdown_requeued"] is True


def test_requeue_running_jobs_for_shutdown_skips_job_without_recovery_context():
    session = _make_active_session()
    job = CompileJob.new(
        workspace_id="ws-reconcile-001",
        project_id="proj-reconcile-001",
        thread_id="thread-reconcile-001",
        profile_id="profile-reconcile-001",
        session_id=session.id,
        metadata={"entry_point": "compile"},
    )
    job.mark_running(session_id=session.id, metadata={"route_kind": "meeting"})
    compile_job_store = FakeCompileJobStore([job])
    meeting_session_store = FakeMeetingSessionStore({session.id: session})

    reconciler = CompileJobReconciler(
        compile_job_store=compile_job_store,
        meeting_session_store=meeting_session_store,
        tasks_store=FakeTasksStore([]),
    )
    summary = reconciler.requeue_running_jobs_for_shutdown(job_ids=[job.id])

    assert summary == {
        "inspected": 1,
        "requeued": 0,
        "session_reset": 0,
        "skipped": 1,
    }
    assert compile_job_store.requeue_calls == []
    assert meeting_session_store.updated_sessions == []


def test_compile_job_dispatch_manager_notify_wakes_consumer():
    class FakeReconciler:
        def __init__(self):
            self.calls = 0
            self.initial_poll_done = asyncio.Event()
            self.notified_poll_done = asyncio.Event()

        async def dispatch_pending_accepted_jobs(self, *, limit):
            self.calls += 1
            if self.calls == 1:
                self.initial_poll_done.set()
                return {
                    "inspected": 0,
                    "resumed": 0,
                    "succeeded": 0,
                    "failed": 0,
                    "session_failed": 0,
                    "skipped": 0,
                }
            self.notified_poll_done.set()
            return {
                "inspected": 1,
                "resumed": 1,
                "succeeded": 0,
                "failed": 0,
                "session_failed": 0,
                "skipped": 0,
            }

    async def _run():
        reconciler = FakeReconciler()
        manager = CompileJobDispatchManager(
            reconciler=reconciler,
            poll_interval_seconds=30.0,
            batch_limit=5,
        )
        manager.start_background_services()
        await asyncio.wait_for(reconciler.initial_poll_done.wait(), timeout=1.0)
        manager.notify_pending_job()
        await asyncio.wait_for(reconciler.notified_poll_done.wait(), timeout=1.0)
        manager.stop_background_services()
        await asyncio.sleep(0)
        assert reconciler.calls >= 2

    asyncio.run(_run())
