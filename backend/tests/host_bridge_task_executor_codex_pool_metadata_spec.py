import base64
import json
import urllib.error

import pytest

from backend.app.services.external_agents.bridge.task_executor import (
    ExecutionContext,
    ExecutionResult,
    HostBridgeTaskExecutor,
)


def _jwt_with_claims(claims: dict) -> str:
    def _part(payload: dict) -> str:
        encoded = base64.urlsafe_b64encode(
            json.dumps(payload, separators=(",", ":")).encode("utf-8")
        ).decode("ascii")
        return encoded.rstrip("=")

    return f"{_part({'alg': 'none'})}.{_part(claims)}."


def test_codex_pool_failure_metadata_preserves_attempted_runtime_context() -> None:
    metadata = HostBridgeTaskExecutor._codex_pool_failure_metadata(
        selected_runtime_id=None,
        attempted_runtime_ids={"runtime-b", "runtime-a"},
        last_runtime_error="You've hit your usage limit.",
        pool_error="No available Codex runtimes in pool",
    )

    assert metadata == {
        "selected_runtime_id": None,
        "attempted_runtime_ids": ["runtime-a", "runtime-b"],
        "last_runtime_error": "You've hit your usage limit.",
        "pool_error": "No available Codex runtimes in pool",
    }


def test_codex_login_prepare_creates_managed_account_home_dirs(tmp_path) -> None:
    account_home = tmp_path / "codex-home-pool" / "accounts" / "acct-new"

    prepared = HostBridgeTaskExecutor._ensure_codex_control_account_home_dirs_sync(
        ExecutionContext(
            execution_id="exec-login",
            workspace_id="ws-test",
            task="login",
            allowed_tools=[],
            max_duration=30,
            control_action="codex_login",
            inputs={"codex_home": str(account_home)},
        )
    )

    assert prepared == account_home
    assert account_home.is_dir()
    assert (account_home / ".config").is_dir()
    assert (account_home / ".local" / "share").is_dir()
    assert (account_home / ".local" / "state").is_dir()
    assert json.loads((account_home / ".mindscape-seed.json").read_text())[
        "created_by"
    ] == "mindscape-host-bridge"


def test_codex_account_home_delete_removes_managed_home(tmp_path) -> None:
    account_home = tmp_path / "codex-home-pool" / "accounts" / "acct-old"
    account_home.mkdir(parents=True)
    (account_home / "auth.json").write_text("{}", encoding="utf-8")

    result = HostBridgeTaskExecutor._delete_codex_control_account_home_sync(
        ExecutionContext(
            execution_id="exec-delete",
            workspace_id="ws-test",
            task="delete",
            allowed_tools=[],
            max_duration=30,
            control_action="codex_account_home_delete",
            inputs={
                "codex_home": str(account_home),
                "runtime_id": "runtime-codex-old",
            },
        )
    )

    assert result.status == "completed"
    assert json.loads(result.output)["home_removed"] is True
    assert not account_home.exists()


def test_codex_oauth_client_id_prefers_id_token_audience() -> None:
    assert (
        HostBridgeTaskExecutor._codex_oauth_client_id(
            {
                "tokens": {
                    "id_token": _jwt_with_claims(
                        {"aud": ["app_EMoamEEZ73f0CkXaXp7hrann"]}
                    )
                }
            }
        )
        == "app_EMoamEEZ73f0CkXaXp7hrann"
    )


@pytest.mark.asyncio
async def test_codex_pool_task_executor_fails_over_after_stale_refresh(
    monkeypatch,
    tmp_path,
):
    executor = HostBridgeTaskExecutor(
        workspace_root=str(tmp_path),
        runtime_surface="codex_cli",
    )
    bundles = [
        {
            "env": {},
            "selected_runtime_id": "runtime-codex-a",
            "available_runtime_count": 2,
            "available_quota_scope_count": 2,
        },
        {
            "env": {},
            "selected_runtime_id": "runtime-codex-b",
            "available_runtime_count": 2,
            "available_quota_scope_count": 2,
        },
    ]
    calls = []

    async def _fake_fetch(runtime_name, ctx, *, excluded_runtime_ids=None):
        calls.append(
            {
                "runtime_name": runtime_name,
                "excluded_runtime_ids": set(excluded_runtime_ids or set()),
            }
        )
        return bundles.pop(0)

    async def _fake_run(*_args, **kwargs):
        if kwargs["selected_runtime_id"] == "runtime-codex-a":
            return ExecutionResult(
                status="failed",
                error=(
                    "Your access token could not be refreshed because your refresh "
                    "token was already used. Please log out and sign in again."
                ),
            )
        return ExecutionResult(status="completed", output="ok")

    async def _fake_progress(*_args, **_kwargs):
        return None

    monkeypatch.setattr(executor, "_resolve_runtime_binary", lambda _name: "/bin/codex")
    monkeypatch.setattr(
        executor,
        "_resolve_cli_runtime_paths",
        lambda _ctx: (str(tmp_path), str(tmp_path), []),
    )
    monkeypatch.setattr(executor, "_fetch_runtime_auth_env", _fake_fetch)
    monkeypatch.setattr(executor, "_run_cli_agent_subprocess", _fake_run)
    monkeypatch.setattr(executor, "_report_progress", _fake_progress)

    result = await executor._execute_via_codex_cli(
        ExecutionContext(
            execution_id="exec-test",
            workspace_id="ws-test",
            task="return ok",
            allowed_tools=[],
            max_duration=30,
        ),
        timeout=30,
    )

    assert result.status == "completed"
    assert result.output == "ok"
    assert calls[1]["excluded_runtime_ids"] == {"runtime-codex-a"}


def test_codex_account_home_probe_refreshes_and_persists_rotated_token(
    monkeypatch,
    tmp_path,
) -> None:
    codex_home = tmp_path / "codex-home"
    codex_home.mkdir()
    auth_path = codex_home / "auth.json"
    auth_path.write_text(
        json.dumps(
            {
                "auth_mode": "chatgpt",
                "tokens": {
                    "access_token": "old-access",
                    "refresh_token": "old-refresh",
                    "id_token": _jwt_with_claims(
                        {"aud": ["app_EMoamEEZ73f0CkXaXp7hrann"]}
                    ),
                    "account_id": "acct-old",
                },
            }
        ),
        encoding="utf-8",
    )

    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def read(self):
            return json.dumps(
                {
                    "access_token": "new-access",
                    "refresh_token": "new-refresh",
                    "id_token": "new-id",
                }
            ).encode("utf-8")

    def fake_urlopen(request, timeout):
        assert timeout == 25
        body = request.data.decode("utf-8")
        assert "grant_type=refresh_token" in body
        assert "refresh_token=old-refresh" in body
        assert "client_id=app_EMoamEEZ73f0CkXaXp7hrann" in body
        return FakeResponse()

    monkeypatch.setattr(
        "backend.app.services.external_agents.bridge.task_executor.urllib.request.urlopen",
        fake_urlopen,
    )

    result = HostBridgeTaskExecutor._codex_probe_token_refresh_sync(
        ExecutionContext(
            execution_id="exec-probe",
            workspace_id="ws-test",
            task="probe",
            allowed_tools=[],
            max_duration=30,
            inputs={
                "runtime_id": "runtime-codex-a",
                "codex_home": str(codex_home),
                "env": {"CODEX_HOME": str(codex_home)},
            },
        )
    )

    saved = json.loads(auth_path.read_text(encoding="utf-8"))
    assert result.status == "completed"
    assert json.loads(result.output)["token_usable"] is True
    assert saved["tokens"]["access_token"] == "new-access"
    assert saved["tokens"]["refresh_token"] == "new-refresh"
    assert saved["tokens"]["id_token"] == "new-id"
    assert saved["tokens"]["account_id"] == "acct-old"


def test_codex_account_home_probe_maps_invalid_grant_to_stale_refresh(
    monkeypatch,
    tmp_path,
) -> None:
    codex_home = tmp_path / "codex-home"
    codex_home.mkdir()
    (codex_home / "auth.json").write_text(
        json.dumps({"tokens": {"refresh_token": "old-refresh"}}),
        encoding="utf-8",
    )

    class ErrorBody:
        def read(self):
            return b'{"error":"invalid_grant","error_description":"Refresh token was already used"}'

        def close(self):
            return None

    def fake_urlopen(_request, timeout):
        assert timeout == 25
        raise urllib.error.HTTPError(
            url="https://auth.openai.com/oauth/token",
            code=400,
            msg="Bad Request",
            hdrs=None,
            fp=ErrorBody(),
        )

    monkeypatch.setattr(
        "backend.app.services.external_agents.bridge.task_executor.urllib.request.urlopen",
        fake_urlopen,
    )

    result = HostBridgeTaskExecutor._codex_probe_token_refresh_sync(
        ExecutionContext(
            execution_id="exec-probe",
            workspace_id="ws-test",
            task="probe",
            allowed_tools=[],
            max_duration=30,
            inputs={
                "runtime_id": "runtime-codex-a",
                "codex_home": str(codex_home),
            },
        )
    )

    assert result.status == "failed"
    assert result.error == "stale_refresh_token: refresh token was already used or rejected"


def test_codex_account_home_probe_maps_empty_401_to_stale_refresh(
    monkeypatch,
    tmp_path,
) -> None:
    codex_home = tmp_path / "codex-home"
    codex_home.mkdir()
    (codex_home / "auth.json").write_text(
        json.dumps({"tokens": {"refresh_token": "old-refresh"}}),
        encoding="utf-8",
    )

    class EmptyBody:
        def read(self):
            return b""

        def close(self):
            return None

    def fake_urlopen(_request, timeout):
        assert timeout == 25
        raise urllib.error.HTTPError(
            url="https://auth.openai.com/oauth/token",
            code=401,
            msg="Unauthorized",
            hdrs=None,
            fp=EmptyBody(),
        )

    monkeypatch.setattr(
        "backend.app.services.external_agents.bridge.task_executor.urllib.request.urlopen",
        fake_urlopen,
    )

    result = HostBridgeTaskExecutor._codex_probe_token_refresh_sync(
        ExecutionContext(
            execution_id="exec-probe",
            workspace_id="ws-test",
            task="probe",
            allowed_tools=[],
            max_duration=30,
            inputs={
                "runtime_id": "runtime-codex-a",
                "codex_home": str(codex_home),
            },
        )
    )

    assert result.status == "failed"
    assert result.error == "stale_refresh_token: refresh token was already used or rejected"
