from types import SimpleNamespace

from backend.app.services import restart_safety


class _FakeResult:
    def __init__(self, value):
        self.value = value

    def scalar(self):
        return self.value


class _FakeConnection:
    def __init__(self, value):
        self.value = value

    def execute(self, _query):
        return _FakeResult(self.value)


def test_count_fresh_meeting_sessions_returns_sql_count():
    assert restart_safety._count_fresh_meeting_sessions(_FakeConnection(2)) == 2


def test_restart_blocker_counts_only_fresh_meeting_sessions(monkeypatch):
    class _Store:
        def get_connection(self):
            class _Ctx:
                def __enter__(self_inner):
                    return _FakeConnection(0)

                def __exit__(self_inner, *_args):
                    return False

            return _Ctx()

    monkeypatch.setattr(
        restart_safety,
        "_count_fresh_meeting_sessions",
        lambda _conn: 0,
    )
    monkeypatch.setattr(
        "app.services.stores.compile_job_store.CompileJobStore",
        lambda: _Store(),
    )

    blockers = restart_safety.inspect_restart_blockers()

    assert blockers["blocked"] is False
    assert blockers["active_meeting_sessions"] == 0
