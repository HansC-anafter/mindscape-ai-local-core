import asyncio
from types import SimpleNamespace

import pytest

from backend.app.services.orchestration.meeting._generation import (
    MeetingGenerationMixin,
    _sanitize_direct_codex_last_message,
)
from backend.app.services.executor_route_resolver import ExecutorRouteSelection


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


@pytest.mark.asyncio
async def test_generate_text_prefers_bound_executor_runtime_over_provider(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    engine = _DummyMeeting()

    async def _fake_executor(messages, model=None):
        return "runtime-owned-output"

    monkeypatch.setattr(engine, "_generate_text_via_executor_runtime", _fake_executor)

    output = await engine._generate_text(
        [
            {"role": "system", "content": "system"},
            {"role": "user", "content": "user"},
        ],
        model="gpt-test",
    )

    assert output == "runtime-owned-output"


@pytest.mark.asyncio
async def test_generate_text_requires_bound_executor_runtime() -> None:
    engine = _DummyMeeting()
    engine.executor_runtime = None

    with pytest.raises(
        RuntimeError,
        match="Meeting generation requires a bound executor runtime",
    ):
        await engine._generate_text(
            [
                {"role": "system", "content": "system"},
                {"role": "user", "content": "user"},
            ],
            model="gpt-test",
        )


@pytest.mark.asyncio
async def test_direct_codex_cli_failsover_to_next_runtime_on_quota(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    engine = _DummyMeeting()
    bundle_calls: list[str] = []
    quota_reports: list[tuple[str, str]] = []
    run_calls: list[str] = []
    success_reports: list[str] = []

    async def _fake_bundle(**kwargs):
        bundle_calls.append("bundle")
        if len(bundle_calls) == 1:
            return {
                "env": {"CODEX_HOME": "/tmp/acct-a"},
                "selected_runtime_id": "runtime-a",
                "effective_workspace_id": "ws-effective",
                "available_quota_scope_count": 2,
            }
        return {
            "env": {"CODEX_HOME": "/tmp/acct-b"},
            "selected_runtime_id": "runtime-b",
            "effective_workspace_id": "ws-effective",
            "available_quota_scope_count": 2,
        }

    async def _fake_run(**kwargs):
        run_calls.append(str(kwargs.get("extra_env", {}).get("CODEX_HOME") or ""))
        if len(run_calls) == 1:
            transcript = (
                "[Meeting Agent Turn]\n"
                "[System Prompt]\nplanner instructions\n"
                "[Turn Prompt]\nscene request\n"
                "ERROR: You've hit your usage limit."
            )
            return (1, transcript, "", "", transcript)
        return (0, "done", "", "done", "done")

    async def _fake_report(
        runtime_id: str,
        *,
        workspace_id: str = "",
        error_text: str = "",
    ) -> None:
        quota_reports.append((runtime_id, workspace_id))

    async def _fake_success(runtime_id: str) -> None:
        success_reports.append(runtime_id)

    monkeypatch.setattr(engine, "_fetch_direct_codex_auth_bundle", _fake_bundle)
    monkeypatch.setattr(engine, "_run_direct_codex_cli_subprocess", _fake_run)
    monkeypatch.setattr(
        engine,
        "_report_direct_codex_runtime_quota_exhausted",
        _fake_report,
    )
    monkeypatch.setattr(
        engine,
        "_report_direct_codex_runtime_success",
        _fake_success,
    )

    output = await engine._generate_text_via_direct_codex_cli(
        [
            {"role": "system", "content": "system"},
            {"role": "user", "content": "user"},
        ],
        model="gpt-test",
    )

    assert output == "done"
    assert len(bundle_calls) == 2
    assert run_calls == ["/tmp/acct-a", "/tmp/acct-b"]
    assert quota_reports == [("runtime-a", "ws-effective")]
    assert success_reports == ["runtime-b"]
    assert engine._bound_direct_codex_auth_bundle is None


@pytest.mark.asyncio
async def test_direct_codex_cli_failsover_to_next_runtime_on_stall_timeout(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    engine = _DummyMeeting()
    bundle_calls: list[str] = []
    auth_reports: list[tuple[str, str, str]] = []
    run_calls: list[str] = []
    success_reports: list[str] = []

    async def _fake_bundle(**kwargs):
        bundle_calls.append("bundle")
        if len(bundle_calls) == 1:
            return {
                "env": {"CODEX_HOME": "/tmp/acct-a"},
                "selected_runtime_id": "runtime-a",
                "effective_workspace_id": "ws-effective",
                "available_quota_scope_count": 2,
            }
        return {
            "env": {"CODEX_HOME": "/tmp/acct-b"},
            "selected_runtime_id": "runtime-b",
            "effective_workspace_id": "ws-effective",
            "available_quota_scope_count": 2,
        }

    async def _fake_run(**kwargs):
        run_calls.append(str(kwargs.get("extra_env", {}).get("CODEX_HOME") or ""))
        if len(run_calls) == 1:
            stalled = "codex_cli subprocess stalled after 45s without file or message activity"
            return (1, "", "", "", stalled)
        return (0, "done", "", "done", "done")

    async def _fake_report(
        runtime_id: str,
        *,
        error_code: str = "401",
        workspace_id: str = "",
    ) -> None:
        auth_reports.append((runtime_id, error_code, workspace_id))

    async def _fake_success(runtime_id: str) -> None:
        success_reports.append(runtime_id)

    monkeypatch.setattr(engine, "_fetch_direct_codex_auth_bundle", _fake_bundle)
    monkeypatch.setattr(engine, "_run_direct_codex_cli_subprocess", _fake_run)
    monkeypatch.setattr(
        engine,
        "_report_direct_codex_runtime_auth_failure",
        _fake_report,
    )
    monkeypatch.setattr(
        engine,
        "_report_direct_codex_runtime_success",
        _fake_success,
    )

    output = await engine._generate_text_via_direct_codex_cli(
        [
            {"role": "system", "content": "system"},
            {"role": "user", "content": "user"},
        ],
        model="gpt-test",
    )

    assert output == "done"
    assert len(bundle_calls) == 2
    assert run_calls == ["/tmp/acct-a", "/tmp/acct-b"]
    assert auth_reports == [("runtime-a", "timeout", "ws-effective")]
    assert success_reports == ["runtime-b"]
    assert engine._bound_direct_codex_auth_bundle is None


@pytest.mark.asyncio
async def test_direct_codex_cli_failsover_to_next_runtime_on_os_error_2(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    engine = _DummyMeeting()
    bundle_calls: list[str] = []
    auth_reports: list[tuple[str, str, str]] = []
    run_calls: list[str] = []
    success_reports: list[str] = []

    async def _fake_bundle(**kwargs):
        bundle_calls.append("bundle")
        if len(bundle_calls) == 1:
            return {
                "env": {"CODEX_HOME": "/tmp/acct-a"},
                "selected_runtime_id": "runtime-a",
                "effective_workspace_id": "ws-effective",
                "available_quota_scope_count": 2,
            }
        return {
            "env": {"CODEX_HOME": "/tmp/acct-b"},
            "selected_runtime_id": "runtime-b",
            "effective_workspace_id": "ws-effective",
            "available_quota_scope_count": 2,
        }

    async def _fake_run(**kwargs):
        run_calls.append(str(kwargs.get("extra_env", {}).get("CODEX_HOME") or ""))
        if len(run_calls) == 1:
            missing = "Error: No such file or directory (os error 2)"
            return (1, "", "", "", missing)
        return (0, "done", "", "done", "done")

    async def _fake_report(
        runtime_id: str,
        *,
        error_code: str = "401",
        workspace_id: str = "",
    ) -> None:
        auth_reports.append((runtime_id, error_code, workspace_id))

    async def _fake_success(runtime_id: str) -> None:
        success_reports.append(runtime_id)

    monkeypatch.setattr(engine, "_fetch_direct_codex_auth_bundle", _fake_bundle)
    monkeypatch.setattr(engine, "_run_direct_codex_cli_subprocess", _fake_run)
    monkeypatch.setattr(
        engine,
        "_report_direct_codex_runtime_auth_failure",
        _fake_report,
    )
    monkeypatch.setattr(
        engine,
        "_report_direct_codex_runtime_success",
        _fake_success,
    )

    output = await engine._generate_text_via_direct_codex_cli(
        [
            {"role": "system", "content": "system"},
            {"role": "user", "content": "user"},
        ],
        model="gpt-test",
    )

    assert output == "done"
    assert len(bundle_calls) == 2
    assert run_calls == ["/tmp/acct-a", "/tmp/acct-b"]
    assert auth_reports == [("runtime-a", "timeout", "ws-effective")]
    assert success_reports == ["runtime-b"]
    assert engine._bound_direct_codex_auth_bundle is None


@pytest.mark.asyncio
async def test_direct_codex_cli_failsover_when_runner_raises_timeout(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    engine = _DummyMeeting()
    bundle_calls: list[str] = []
    auth_reports: list[tuple[str, str, str]] = []
    run_calls: list[str] = []
    success_reports: list[str] = []

    async def _fake_bundle(**kwargs):
        bundle_calls.append("bundle")
        if len(bundle_calls) == 1:
            return {
                "env": {"CODEX_HOME": "/tmp/acct-a"},
                "selected_runtime_id": "runtime-a",
                "effective_workspace_id": "ws-effective",
                "available_quota_scope_count": 2,
            }
        return {
            "env": {"CODEX_HOME": "/tmp/acct-b"},
            "selected_runtime_id": "runtime-b",
            "effective_workspace_id": "ws-effective",
            "available_quota_scope_count": 2,
        }

    async def _fake_shared_run(**kwargs):
        run_calls.append(str(kwargs.get("env", {}).get("CODEX_HOME") or ""))
        if len(run_calls) == 1:
            raise asyncio.TimeoutError(
                "codex_cli subprocess stalled after 45s without file or message activity"
            )
        return SimpleNamespace(
            returncode=0,
            stdout_text="done",
            stderr_text="",
            output_text="done",
            combined_output="done",
            synthesized_error=None,
        )

    async def _fake_report(
        runtime_id: str,
        *,
        error_code: str = "401",
        workspace_id: str = "",
    ) -> None:
        auth_reports.append((runtime_id, error_code, workspace_id))

    async def _fake_success(runtime_id: str) -> None:
        success_reports.append(runtime_id)

    monkeypatch.setattr(engine, "_fetch_direct_codex_auth_bundle", _fake_bundle)
    monkeypatch.setattr(
        "backend.app.services.orchestration.meeting._generation._run_shared_codex_cli_subprocess",
        _fake_shared_run,
    )
    monkeypatch.setattr(
        engine,
        "_report_direct_codex_runtime_auth_failure",
        _fake_report,
    )
    monkeypatch.setattr(
        engine,
        "_report_direct_codex_runtime_success",
        _fake_success,
    )

    output = await engine._generate_text_via_direct_codex_cli(
        [
            {"role": "system", "content": "system"},
            {"role": "user", "content": "user"},
        ],
        model="gpt-test",
    )

    assert output == "done"
    assert len(bundle_calls) == 2
    assert run_calls == ["/tmp/acct-a", "/tmp/acct-b"]
    assert auth_reports == [("runtime-a", "timeout", "ws-effective")]
    assert success_reports == ["runtime-b"]
    assert engine._bound_direct_codex_auth_bundle is None


@pytest.mark.asyncio
async def test_direct_codex_cli_reports_deactivated_workspace_error_code(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    engine = _DummyMeeting()
    auth_reports: list[tuple[str, str, str]] = []

    async def _fake_bundle(**kwargs):
        return {
            "env": {"CODEX_HOME": "/tmp/acct-a"},
            "selected_runtime_id": "runtime-a",
            "effective_workspace_id": "ws-effective",
            "available_quota_scope_count": 1,
        }

    async def _fake_run(**kwargs):
        transcript = (
            "402 Payment Required\n"
            '{"code":"deactivated_workspace","message":"workspace disabled"}'
        )
        return (1, transcript, "", "", transcript)

    async def _fake_report(
        runtime_id: str,
        *,
        error_code: str = "401",
        workspace_id: str = "",
    ) -> None:
        auth_reports.append((runtime_id, error_code, workspace_id))

    monkeypatch.setattr(engine, "_fetch_direct_codex_auth_bundle", _fake_bundle)
    monkeypatch.setattr(engine, "_run_direct_codex_cli_subprocess", _fake_run)
    monkeypatch.setattr(
        engine,
        "_report_direct_codex_runtime_auth_failure",
        _fake_report,
    )

    with pytest.raises(RuntimeError, match="deactivated_workspace"):
        await engine._generate_text_via_direct_codex_cli(
            [
                {"role": "system", "content": "system"},
                {"role": "user", "content": "user"},
            ],
            model="gpt-test",
        )

    assert auth_reports == [("runtime-a", "deactivated_workspace", "ws-effective")]


def test_sanitize_direct_codex_last_message_rejects_transcript_echo() -> None:
    polluted = (
        "[Meeting Agent Turn]\n"
        "[System Prompt]\nplanner instructions\n"
        "[Turn Prompt]\nscene request\n"
        '{"decision_summary":"echo"}'
    )

    assert _sanitize_direct_codex_last_message(polluted) == ""


@pytest.mark.asyncio
async def test_fetch_direct_codex_auth_bundle_allows_pool_fallback_for_preferred_runtime(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    engine = _DummyMeeting()
    call_kwargs: dict[str, object] = {}
    binding_calls: list[dict[str, object]] = []

    class _FakeResolver:
        def resolve(self, **kwargs):
            assert kwargs == {
                "surface": "codex_cli",
                "workspace_id": "ws-123",
                "auth_workspace_id": None,
                "source_workspace_id": None,
            }
            return ExecutorRouteSelection(
                surface="codex_cli",
                executor_runtime="codex_cli",
                preferred_runtime_id="runtime-preferred",
                requested_workspace_id="ws-123",
                effective_workspace_id="ws-123",
                auth_workspace_id="ws-123",
                source_workspace_id="ws-123",
                selection_reason="preferred",
                trace=({"via": "preferred"},),
            )

    class _FakeBindingService:
        def resolve_pool_preference(
            self,
            *,
            selection,
            lease_owner_type=None,
            lease_owner_id=None,
        ):
            return {
                "preferred_runtime_id": selection.preferred_runtime_id,
                "allow_runtime_substitution": False,
                "preference_source": "executor_route",
                "binding_runtime_id": None,
                "binding_state": "configured",
            }

        def record_route_resolution(self, *, selection, resolved_runtime_id):
            binding_calls.append(
                {
                    "surface": selection.surface,
                    "resolved_runtime_id": resolved_runtime_id,
                    "policy_mode": selection.policy_mode,
                }
            )
            return None

        def record_runtime_lease(
            self,
            *,
            workspace_id,
            surface,
            runtime_id,
            lease_owner_type,
            lease_owner_id,
        ):
            binding_calls.append(
                {
                    "surface": surface,
                    "runtime_id": runtime_id,
                    "lease_owner_type": lease_owner_type,
                    "lease_owner_id": lease_owner_id,
                    "workspace_id": workspace_id,
                }
            )
            return None

    class _FakePoolService:
        def get_active_auth_bundle(
            self,
            *,
            preferred_runtime_id: str | None = None,
            allow_runtime_substitution: bool = False,
            excluded_runtime_ids=None,
            excluded_quota_scope_keys=None,
            require_probe_available=False,
        ):
            call_kwargs["preferred_runtime_id"] = preferred_runtime_id
            call_kwargs["allow_runtime_substitution"] = allow_runtime_substitution
            return {
                "env": {"CODEX_HOME": "/tmp/acct-b"},
                "selected_runtime_id": "runtime-preferred",
                "available_quota_scope_count": 2,
                "probe_state": "available",
                "last_probe_success_at": "2026-05-08T00:00:00+00:00",
            }

    class _FakeAdmissionService:
        def evaluate_execution_admission(
            self,
            *,
            preferred_runtime_id=None,
            allow_runtime_substitution=True,
            require_probe_available=False,
        ):
            return SimpleNamespace(
                admissible=True,
                to_payload=lambda: {"admissible": True},
            )

    async def _fake_to_thread(func, *args, **kwargs):
        return func(*args, **kwargs)

    monkeypatch.setattr(
        "backend.app.services.executor_route_resolver.ExecutorRouteResolver",
        _FakeResolver,
    )
    monkeypatch.setattr(
        "backend.app.services.executor_binding_service.ExecutorBindingService",
        _FakeBindingService,
    )
    monkeypatch.setattr(
        "backend.app.services.codex_pool_service.CodexPoolService",
        _FakePoolService,
    )
    monkeypatch.setattr(
        "backend.app.services.codex_pool_admission_service.CodexPoolAdmissionService",
        _FakeAdmissionService,
    )
    monkeypatch.setattr(
        "backend.app.services.orchestration.meeting._generation.asyncio.to_thread",
        _fake_to_thread,
    )

    bundle = await engine._fetch_direct_codex_auth_bundle()

    assert bundle["selected_runtime_id"] == "runtime-preferred"
    assert bundle["requested_workspace_id"] == "ws-123"
    assert bundle["preference_source"] == "executor_route"
    assert call_kwargs == {
        "preferred_runtime_id": "runtime-preferred",
        "allow_runtime_substitution": False,
    }
    assert binding_calls == [
        {
            "surface": "codex_cli",
            "resolved_runtime_id": "runtime-preferred",
            "policy_mode": "pinned_runtime",
        },
        {
            "surface": "codex_cli",
            "runtime_id": "runtime-preferred",
            "lease_owner_type": "meeting_session",
            "lease_owner_id": "sess-123",
            "workspace_id": "ws-123",
        },
    ]


@pytest.mark.asyncio
async def test_fetch_direct_codex_auth_bundle_pins_workspace_pool_selection(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    engine = _DummyMeeting()
    pool_calls: list[int] = []
    binding_calls: list[dict[str, object]] = []
    lease_state: dict[str, str | None] = {"runtime_id": None}

    class _FakeResolver:
        def resolve(self, **kwargs):
            assert kwargs == {
                "surface": "codex_cli",
                "workspace_id": "ws-123",
                "auth_workspace_id": None,
                "source_workspace_id": None,
            }
            return ExecutorRouteSelection(
                surface="codex_cli",
                executor_runtime="codex_cli",
                preferred_runtime_id=None,
                requested_workspace_id="ws-123",
                effective_workspace_id="ws-123",
                auth_workspace_id="ws-123",
                source_workspace_id="ws-123",
                selection_reason="workspace_pool",
                trace=({"via": "workspace_pool"},),
            )

    class _FakeBindingService:
        def load_binding_snapshot(self, *, workspace_id, surface):
            assert workspace_id == "ws-123"
            assert surface == "codex_cli"
            if not lease_state["runtime_id"]:
                return None
            return {
                "binding_state": "resolved",
                "lease_state": "active",
                "lease_owner_type": "meeting_session",
                "lease_owner_id": "sess-123",
                "lease_runtime_id": lease_state["runtime_id"],
            }

        def resolve_pool_preference(
            self,
            *,
            selection,
            lease_owner_type=None,
            lease_owner_id=None,
        ):
            binding_calls.append(
                {
                    "surface": selection.surface,
                    "preference_source": "pool_rotation",
                    "policy_mode": selection.policy_mode,
                    "lease_owner_type": lease_owner_type,
                    "lease_owner_id": lease_owner_id,
                }
            )
            return {
                "preferred_runtime_id": None,
                "allow_runtime_substitution": True,
                "preference_source": "pool_rotation",
                "binding_runtime_id": None,
                "binding_state": "configured",
            }

        def record_route_resolution(self, *, selection, resolved_runtime_id):
            binding_calls.append(
                {
                    "surface": selection.surface,
                    "resolved_runtime_id": resolved_runtime_id,
                    "policy_mode": selection.policy_mode,
                }
            )
            return None

        def record_runtime_lease(
            self,
            *,
            workspace_id,
            surface,
            runtime_id,
            lease_owner_type,
            lease_owner_id,
        ):
            lease_state["runtime_id"] = runtime_id
            binding_calls.append(
                {
                    "surface": surface,
                    "runtime_id": runtime_id,
                    "lease_owner_type": lease_owner_type,
                    "lease_owner_id": lease_owner_id,
                    "workspace_id": workspace_id,
                }
            )
            return None

    class _FakePoolService:
        def get_active_auth_bundle(
            self,
            *,
            preferred_runtime_id: str | None = None,
            allow_runtime_substitution: bool = False,
            excluded_runtime_ids=None,
            excluded_quota_scope_keys=None,
            require_probe_available=False,
        ):
            pool_calls.append(1)
            assert preferred_runtime_id is None
            assert allow_runtime_substitution is True
            return {
                "env": {"CODEX_HOME": "/tmp/acct-a"},
                "selected_runtime_id": "runtime-a",
                "available_quota_scope_count": 4,
                "probe_state": "available",
                "last_probe_success_at": "2026-05-08T00:00:00+00:00",
            }

    class _FakeAdmissionService:
        def evaluate_execution_admission(
            self,
            *,
            preferred_runtime_id=None,
            allow_runtime_substitution=True,
            require_probe_available=False,
        ):
            return SimpleNamespace(
                admissible=True,
                to_payload=lambda: {"admissible": True},
            )

    async def _fake_to_thread(func, *args, **kwargs):
        return func(*args, **kwargs)

    monkeypatch.setattr(
        "backend.app.services.executor_route_resolver.ExecutorRouteResolver",
        _FakeResolver,
    )
    monkeypatch.setattr(
        "backend.app.services.executor_binding_service.ExecutorBindingService",
        _FakeBindingService,
    )
    monkeypatch.setattr(
        "backend.app.services.codex_pool_service.CodexPoolService",
        _FakePoolService,
    )
    monkeypatch.setattr(
        "backend.app.services.codex_pool_admission_service.CodexPoolAdmissionService",
        _FakeAdmissionService,
    )
    monkeypatch.setattr(
        "backend.app.services.orchestration.meeting._generation.asyncio.to_thread",
        _fake_to_thread,
    )

    first = await engine._fetch_direct_codex_auth_bundle()
    second = await engine._fetch_direct_codex_auth_bundle()

    assert first["selected_runtime_id"] == "runtime-a"
    assert second["selected_runtime_id"] == "runtime-a"
    assert len(pool_calls) == 1
    assert binding_calls == [
        {
            "surface": "codex_cli",
            "preference_source": "pool_rotation",
            "policy_mode": "pool_rotation",
            "lease_owner_type": "meeting_session",
            "lease_owner_id": "sess-123",
        },
        {
            "surface": "codex_cli",
            "resolved_runtime_id": "runtime-a",
            "policy_mode": "pool_rotation",
        },
        {
            "surface": "codex_cli",
            "runtime_id": "runtime-a",
            "lease_owner_type": "meeting_session",
            "lease_owner_id": "sess-123",
            "workspace_id": "ws-123",
        },
    ]


@pytest.mark.asyncio
async def test_fetch_direct_codex_auth_bundle_rebinds_sticky_runtime_when_unavailable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    engine = _DummyMeeting()
    pool_calls: list[dict[str, object]] = []
    binding_calls: list[dict[str, object]] = []

    class _FakeResolver:
        def resolve(self, **kwargs):
            assert kwargs == {
                "surface": "codex_cli",
                "workspace_id": "ws-123",
                "auth_workspace_id": None,
                "source_workspace_id": None,
            }
            return ExecutorRouteSelection(
                surface="codex_cli",
                executor_runtime="codex_cli",
                preferred_runtime_id=None,
                requested_workspace_id="ws-123",
                effective_workspace_id="ws-123",
                auth_workspace_id="ws-123",
                source_workspace_id="ws-123",
                selection_reason="workspace_pool",
                trace=({"via": "workspace_pool"},),
            )

    class _FakeBindingService:
        def resolve_pool_preference(
            self,
            *,
            selection,
            lease_owner_type=None,
            lease_owner_id=None,
        ):
            return {
                "preferred_runtime_id": "runtime-old",
                "allow_runtime_substitution": False,
                "preference_source": "binding_snapshot",
                "binding_runtime_id": "runtime-old",
                "binding_state": "resolved",
            }

        def record_route_resolution(self, *, selection, resolved_runtime_id):
            binding_calls.append(
                {
                    "surface": selection.surface,
                    "resolved_runtime_id": resolved_runtime_id,
                    "policy_mode": selection.policy_mode,
                }
            )
            return None

        def record_runtime_lease(
            self,
            *,
            workspace_id,
            surface,
            runtime_id,
            lease_owner_type,
            lease_owner_id,
        ):
            binding_calls.append(
                {
                    "surface": surface,
                    "runtime_id": runtime_id,
                    "lease_owner_type": lease_owner_type,
                    "lease_owner_id": lease_owner_id,
                    "workspace_id": workspace_id,
                }
            )
            return None

    class _FakePoolService:
        def get_active_auth_bundle(
            self,
            *,
            preferred_runtime_id: str | None = None,
            allow_runtime_substitution: bool = False,
            excluded_runtime_ids=None,
            excluded_quota_scope_keys=None,
            require_probe_available=False,
        ):
            pool_calls.append(
                {
                    "preferred_runtime_id": preferred_runtime_id,
                    "allow_runtime_substitution": allow_runtime_substitution,
                }
            )
            if preferred_runtime_id == "runtime-old":
                return {"error": "Preferred Codex runtime unavailable: runtime-old"}
            return {
                "env": {"CODEX_HOME": "/tmp/acct-b"},
                "selected_runtime_id": "runtime-new",
                "available_quota_scope_count": 2,
                "probe_state": "available",
                "last_probe_success_at": "2026-05-08T00:00:00+00:00",
            }

    class _FakeAdmissionService:
        def evaluate_execution_admission(
            self,
            *,
            preferred_runtime_id=None,
            allow_runtime_substitution=True,
            require_probe_available=False,
        ):
            return SimpleNamespace(
                admissible=True,
                to_payload=lambda: {"admissible": True},
            )

    async def _fake_to_thread(func, *args, **kwargs):
        return func(*args, **kwargs)

    monkeypatch.setattr(
        "backend.app.services.executor_route_resolver.ExecutorRouteResolver",
        _FakeResolver,
    )
    monkeypatch.setattr(
        "backend.app.services.executor_binding_service.ExecutorBindingService",
        _FakeBindingService,
    )
    monkeypatch.setattr(
        "backend.app.services.codex_pool_service.CodexPoolService",
        _FakePoolService,
    )
    monkeypatch.setattr(
        "backend.app.services.codex_pool_admission_service.CodexPoolAdmissionService",
        _FakeAdmissionService,
    )
    monkeypatch.setattr(
        "backend.app.services.orchestration.meeting._generation.asyncio.to_thread",
        _fake_to_thread,
    )

    bundle = await engine._fetch_direct_codex_auth_bundle()

    assert pool_calls == [
        {
            "preferred_runtime_id": "runtime-old",
            "allow_runtime_substitution": False,
        },
        {
            "preferred_runtime_id": None,
            "allow_runtime_substitution": True,
        },
    ]
    assert binding_calls == [
        {
            "surface": "codex_cli",
            "resolved_runtime_id": "runtime-new",
            "policy_mode": "pool_rotation",
        },
        {
            "surface": "codex_cli",
            "runtime_id": "runtime-new",
            "lease_owner_type": "meeting_session",
            "lease_owner_id": "sess-123",
            "workspace_id": "ws-123",
        },
    ]
    assert bundle["selected_runtime_id"] == "runtime-new"
    assert bundle["preference_source"] == "binding_rebind"


@pytest.mark.asyncio
async def test_fetch_direct_codex_auth_bundle_rebinds_session_lease_when_pool_falls_through(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    engine = _DummyMeeting()
    pool_calls: list[dict[str, object]] = []
    binding_calls: list[dict[str, object]] = []

    class _FakeResolver:
        def resolve(self, **kwargs):
            return ExecutorRouteSelection(
                surface="codex_cli",
                executor_runtime="codex_cli",
                preferred_runtime_id=None,
                requested_workspace_id="ws-123",
                effective_workspace_id="ws-123",
                auth_workspace_id="ws-123",
                source_workspace_id="ws-123",
                selection_reason="workspace_pool",
                trace=({"via": "workspace_pool"},),
            )

    class _FakeBindingService:
        def resolve_pool_preference(
            self,
            *,
            selection,
            lease_owner_type=None,
            lease_owner_id=None,
        ):
            return {
                "preferred_runtime_id": "runtime-old",
                "allow_runtime_substitution": True,
                "preference_source": "session_lease",
                "binding_runtime_id": "runtime-old",
                "binding_state": "resolved",
                "lease_runtime_id": "runtime-old",
                "lease_state": "active",
                "lease_owner_type": lease_owner_type,
                "lease_owner_id": lease_owner_id,
            }

        def record_route_resolution(self, *, selection, resolved_runtime_id):
            binding_calls.append(
                {
                    "surface": selection.surface,
                    "resolved_runtime_id": resolved_runtime_id,
                    "policy_mode": selection.policy_mode,
                }
            )
            return None

        def record_runtime_lease(
            self,
            *,
            workspace_id,
            surface,
            runtime_id,
            lease_owner_type,
            lease_owner_id,
        ):
            binding_calls.append(
                {
                    "surface": surface,
                    "runtime_id": runtime_id,
                    "lease_owner_type": lease_owner_type,
                    "lease_owner_id": lease_owner_id,
                    "workspace_id": workspace_id,
                }
            )
            return None

        def clear_runtime_lease(self, **kwargs):
            raise AssertionError("session lease should rebind in-place, not clear first")

    class _FakePoolService:
        def get_active_auth_bundle(
            self,
            *,
            preferred_runtime_id: str | None = None,
            allow_runtime_substitution: bool = False,
            excluded_runtime_ids=None,
            excluded_quota_scope_keys=None,
            require_probe_available=False,
        ):
            pool_calls.append(
                {
                    "preferred_runtime_id": preferred_runtime_id,
                    "allow_runtime_substitution": allow_runtime_substitution,
                }
            )
            assert preferred_runtime_id == "runtime-old"
            assert allow_runtime_substitution is True
            return {
                "env": {"CODEX_HOME": "/tmp/acct-b"},
                "selected_runtime_id": "runtime-new",
                "available_quota_scope_count": 2,
                "probe_state": "available",
                "last_probe_success_at": "2026-05-08T00:00:00+00:00",
            }

    class _FakeAdmissionService:
        def evaluate_execution_admission(
            self,
            *,
            preferred_runtime_id=None,
            allow_runtime_substitution=True,
            require_probe_available=False,
        ):
            return SimpleNamespace(
                admissible=True,
                to_payload=lambda: {"admissible": True},
            )

    async def _fake_to_thread(func, *args, **kwargs):
        return func(*args, **kwargs)

    monkeypatch.setattr(
        "backend.app.services.executor_route_resolver.ExecutorRouteResolver",
        _FakeResolver,
    )
    monkeypatch.setattr(
        "backend.app.services.executor_binding_service.ExecutorBindingService",
        _FakeBindingService,
    )
    monkeypatch.setattr(
        "backend.app.services.codex_pool_service.CodexPoolService",
        _FakePoolService,
    )
    monkeypatch.setattr(
        "backend.app.services.codex_pool_admission_service.CodexPoolAdmissionService",
        _FakeAdmissionService,
    )
    monkeypatch.setattr(
        "backend.app.services.orchestration.meeting._generation.asyncio.to_thread",
        _fake_to_thread,
    )

    bundle = await engine._fetch_direct_codex_auth_bundle()

    assert pool_calls == [
        {
            "preferred_runtime_id": "runtime-old",
            "allow_runtime_substitution": True,
        }
    ]
    assert bundle["selected_runtime_id"] == "runtime-new"
    assert bundle["preference_source"] == "lease_rebind"
    assert binding_calls == [
        {
            "surface": "codex_cli",
            "resolved_runtime_id": "runtime-new",
            "policy_mode": "pool_rotation",
        },
        {
            "surface": "codex_cli",
            "runtime_id": "runtime-new",
            "lease_owner_type": "meeting_session",
            "lease_owner_id": "sess-123",
            "workspace_id": "ws-123",
        },
    ]


@pytest.mark.asyncio
async def test_fetch_direct_codex_auth_bundle_blocks_when_admission_finds_no_healthy_runtime(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    engine = _DummyMeeting()

    class _FakeResolver:
        def resolve(self, **kwargs):
            return ExecutorRouteSelection(
                surface="codex_cli",
                executor_runtime="codex_cli",
                preferred_runtime_id=None,
                requested_workspace_id="ws-123",
                effective_workspace_id="ws-123",
                auth_workspace_id="ws-123",
                source_workspace_id="ws-123",
                selection_reason="workspace_pool",
                trace=({"via": "workspace_pool"},),
            )

    class _FakeBindingService:
        def resolve_pool_preference(
            self,
            *,
            selection,
            lease_owner_type=None,
            lease_owner_id=None,
        ):
            return {
                "preferred_runtime_id": None,
                "allow_runtime_substitution": True,
                "preference_source": "pool_rotation",
                "binding_runtime_id": None,
                "binding_state": "configured",
            }

    class _ExplodingPoolService:
        def get_active_auth_bundle(self, **kwargs):
            raise AssertionError("pool selection should not run when admission blocks")

    class _FakeAdmissionDecision:
        admissible = False

        @staticmethod
        def blocker_message():
            return "Codex pool admission blocked: no_healthy_runtimes"

        @staticmethod
        def to_payload():
            return {
                "admissible": False,
                "reason": "no_healthy_runtimes",
                "healthy_runtime_count": 0,
            }

    class _FakeAdmissionService:
        def evaluate_execution_admission(
            self,
            *,
            preferred_runtime_id=None,
            allow_runtime_substitution=True,
            require_probe_available=False,
        ):
            return _FakeAdmissionDecision()

    async def _fake_to_thread(func, *args, **kwargs):
        return func(*args, **kwargs)

    monkeypatch.setattr(
        "backend.app.services.executor_route_resolver.ExecutorRouteResolver",
        _FakeResolver,
    )
    monkeypatch.setattr(
        "backend.app.services.executor_binding_service.ExecutorBindingService",
        _FakeBindingService,
    )
    monkeypatch.setattr(
        "backend.app.services.codex_pool_service.CodexPoolService",
        _ExplodingPoolService,
    )
    monkeypatch.setattr(
        "backend.app.services.codex_pool_admission_service.CodexPoolAdmissionService",
        _FakeAdmissionService,
    )
    monkeypatch.setattr(
        "backend.app.services.orchestration.meeting._generation.asyncio.to_thread",
        _fake_to_thread,
    )

    bundle = await engine._fetch_direct_codex_auth_bundle()

    assert bundle["error"] == "Codex pool admission blocked: no_healthy_runtimes"
    assert bundle["admission"]["reason"] == "no_healthy_runtimes"
