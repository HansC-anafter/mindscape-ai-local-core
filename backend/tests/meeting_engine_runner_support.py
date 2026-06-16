from backend.app.models.meeting_command import MeetingCommandRecord, MeetingCommandStatus


class _FakeRuntimeProfile:
    model_name = "runtime-model"
    default_model = None
    loop_budget = None
    recovery_policy = None

    def ensure_phase2_fields(self):
        return None


class _FakeWorkspaceRuntimeProfileStore:
    async def get_runtime_profile(self, workspace_id):
        return None

    async def create_default_profile(self, workspace_id):
        return _FakeRuntimeProfile()


class _FakeSessionStore:
    def __init__(self):
        self.updated = []

    def update(self, session):
        self.updated.append(session)
        return session


class _FakeArtifactsStore:
    def __init__(self):
        self.created = []
        self.by_id = {}
        self.by_execution_id = {}

    def get_artifact(self, artifact_id):
        return self.by_id.get(artifact_id)

    def get_by_execution_id(self, execution_id):
        artifacts = self.list_by_execution_id(execution_id)
        return artifacts[0] if artifacts else None

    def list_by_execution_id(self, execution_id):
        artifacts = self.by_execution_id.get(execution_id)
        if artifacts is None:
            return []
        if isinstance(artifacts, list):
            return artifacts
        return [artifacts]

    def create_artifact(self, artifact):
        self.created.append(artifact)
        self.by_id[artifact.id] = artifact
        return artifact


def _command() -> MeetingCommandRecord:
    return MeetingCommandRecord(
        command_id="cmd_runner",
        workspace_id="ws_demo",
        meeting_id="mtg_demo",
        thread_id="thread_demo",
        origin_surface="meeting_workbench",
        actor="user",
        intent_text="Run meeting orchestration",
        status=MeetingCommandStatus.ACCEPTED,
    )
