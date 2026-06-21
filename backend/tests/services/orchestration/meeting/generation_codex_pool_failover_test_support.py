from types import SimpleNamespace

from backend.app.services.orchestration.meeting._generation import MeetingGenerationMixin


class _DummyMeeting(MeetingGenerationMixin):
    def __init__(self) -> None:
        self.session = SimpleNamespace(id="sess-123")
        self.workspace = SimpleNamespace(id="ws-123")
        self.executor_runtime = "codex_cli"
        self.max_retries = 0
        self.orchestrator = SimpleNamespace(record_retry=lambda: None)

    async def _emit_meeting_stage(self, stage: str, message: str) -> None:
        return None

    def _emit_runtime_unavailable_event(
        self,
        *,
        runtime_id: str,
        error: str,
        reason: str,
    ) -> None:
        return None
