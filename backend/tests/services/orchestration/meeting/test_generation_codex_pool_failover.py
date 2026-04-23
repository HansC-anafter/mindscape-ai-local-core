from types import SimpleNamespace

import pytest

from backend.app.services.orchestration.meeting._generation import (
    MeetingGenerationMixin,
)


class _DummyMeeting(MeetingGenerationMixin):
    def __init__(self) -> None:
        self.session = SimpleNamespace(id="sess-123")
        self.workspace = SimpleNamespace(id="ws-123")

    async def _emit_meeting_stage(self, stage: str, message: str) -> None:
        return None


@pytest.mark.asyncio
async def test_direct_codex_cli_uses_pool_failover(monkeypatch: pytest.MonkeyPatch) -> None:
    engine = _DummyMeeting()
    bundle_calls: list[int] = []
    quota_reports: list[str] = []

    async def _fake_bundle():
        bundle_calls.append(1)
        if len(bundle_calls) == 1:
            return {
                "env": {"CODEX_HOME": "/tmp/acct-a"},
                "selected_runtime_id": "runtime-a",
                "available_quota_scope_count": 2,
            }
        return {
            "env": {"CODEX_HOME": "/tmp/acct-b"},
            "selected_runtime_id": "runtime-b",
            "available_quota_scope_count": 2,
        }

    async def _fake_run(**kwargs):
        selected_home = (kwargs.get("extra_env") or {}).get("CODEX_HOME")
        if selected_home == "/tmp/acct-a":
            return (
                1,
                "",
                "You've hit your usage limit. Try again later.",
                "",
                "You've hit your usage limit. Try again later.",
            )
        return (0, "", "", "native meeting output", "native meeting output")

    async def _fake_report(runtime_id: str) -> None:
        quota_reports.append(runtime_id)

    monkeypatch.setattr(engine, "_fetch_direct_codex_auth_bundle", _fake_bundle)
    monkeypatch.setattr(engine, "_run_direct_codex_cli_subprocess", _fake_run)
    monkeypatch.setattr(
        engine,
        "_report_direct_codex_runtime_quota_exhausted",
        _fake_report,
    )

    output = await engine._generate_text_via_direct_codex_cli(
        [
            {"role": "system", "content": "system"},
            {"role": "user", "content": "user"},
        ],
        model="gpt-test",
    )

    assert output == "native meeting output"
    assert len(bundle_calls) == 2
    assert quota_reports == ["runtime-a"]
