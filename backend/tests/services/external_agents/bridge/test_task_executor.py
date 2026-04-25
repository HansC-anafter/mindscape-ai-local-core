import json
import urllib.error
import urllib.parse
import urllib.request

from backend.app.services.external_agents.bridge.task_executor import (
    ExecutionContext,
    HostBridgeTaskExecutor,
)


def _make_context() -> ExecutionContext:
    return ExecutionContext(
        execution_id="exec-1",
        workspace_id="ws-1",
        task="do the task",
        allowed_tools=[],
        max_duration=300,
        auth_workspace_id="auth-ws",
        source_workspace_id="src-ws",
    )


def test_task_executor_resolve_backend_api_urls_expands_loopback_candidates(monkeypatch):
    monkeypatch.setenv("MINDSCAPE_BACKEND_API_URL", "http://localhost:8220")

    urls = HostBridgeTaskExecutor._resolve_backend_api_urls()

    assert urls[0] == "http://localhost:8220"
    assert urls[1] == "http://127.0.0.1:8220"
    assert "http://0.0.0.0:8220" in urls
    assert "http://host.docker.internal:8220" in urls


def test_task_executor_fetch_runtime_auth_bundle_tries_backend_candidates(
    monkeypatch, tmp_path
):
    monkeypatch.setenv("MINDSCAPE_BACKEND_API_URL", "http://localhost:8220")

    executor = HostBridgeTaskExecutor(
        workspace_root=str(tmp_path),
        runtime_surface="codex_cli",
    )
    ctx = _make_context()
    seen_urls = []

    class _FakeResponse:
        def __init__(self, payload):
            self._payload = json.dumps(payload).encode("utf-8")

        def read(self):
            return self._payload

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

    def _fake_urlopen(req, timeout=0):
        del timeout
        seen_urls.append(req.full_url)
        if req.full_url.startswith("http://localhost:8220"):
            raise urllib.error.URLError("timed out")
        return _FakeResponse(
            {
                "auth_mode": "backend",
                "selected_runtime_id": "runtime-2",
                "env": {
                    "OPENAI_API_KEY": "test-key",
                    "EMPTY_VALUE": "",
                },
            }
        )

    monkeypatch.setattr(urllib.request, "urlopen", _fake_urlopen)

    bundle = executor._fetch_runtime_auth_bundle_sync("codex_cli", ctx)

    assert seen_urls[0].startswith("http://localhost:8220/api/v1/auth/cli-token?")
    assert seen_urls[1].startswith("http://127.0.0.1:8220/api/v1/auth/cli-token?")
    parsed = urllib.parse.urlparse(seen_urls[1])
    params = urllib.parse.parse_qs(parsed.query)
    assert params["workspace_id"] == ["ws-1"]
    assert params["auth_workspace_id"] == ["auth-ws"]
    assert params["source_workspace_id"] == ["src-ws"]
    assert bundle["selected_runtime_id"] == "runtime-2"
    assert bundle["env"] == {"OPENAI_API_KEY": "test-key"}


def test_task_executor_reports_quota_with_effective_workspace_binding(
    monkeypatch, tmp_path
):
    monkeypatch.setenv("MINDSCAPE_BACKEND_API_URL", "http://localhost:8220")

    executor = HostBridgeTaskExecutor(
        workspace_root=str(tmp_path),
        runtime_surface="codex_cli",
    )
    seen_urls = []

    class _FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

    def _fake_urlopen(req, timeout=0):
        del timeout
        seen_urls.append(req.full_url)
        return _FakeResponse()

    monkeypatch.setattr(urllib.request, "urlopen", _fake_urlopen)

    executor._report_runtime_quota_exhausted_sync(
        "codex_cli",
        "runtime-2",
        workspace_id="ws-requested",
        effective_workspace_id="ws-effective",
    )

    parsed = urllib.parse.urlparse(seen_urls[0])
    params = urllib.parse.parse_qs(parsed.query)
    assert parsed.path == "/api/v1/auth/runtime-quota-exhausted"
    assert params["surface"] == ["codex_cli"]
    assert params["runtime_id"] == ["runtime-2"]
    assert params["workspace_id"] == ["ws-requested"]
    assert params["effective_workspace_id"] == ["ws-effective"]


def test_task_executor_reports_runtime_success(monkeypatch, tmp_path):
    monkeypatch.setenv("MINDSCAPE_BACKEND_API_URL", "http://localhost:8220")

    executor = HostBridgeTaskExecutor(
        workspace_root=str(tmp_path),
        runtime_surface="codex_cli",
    )
    seen_urls = []

    class _FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

    def _fake_urlopen(req, timeout=0):
        del timeout
        seen_urls.append(req.full_url)
        return _FakeResponse()

    monkeypatch.setattr(urllib.request, "urlopen", _fake_urlopen)

    executor._report_runtime_success_sync(
        "codex_cli",
        "runtime-2",
    )

    parsed = urllib.parse.urlparse(seen_urls[0])
    params = urllib.parse.parse_qs(parsed.query)
    assert parsed.path == "/api/v1/auth/runtime-success"
    assert params["surface"] == ["codex_cli"]
    assert params["runtime_id"] == ["runtime-2"]
