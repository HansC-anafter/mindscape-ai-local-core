import json
import os
import sys
from typing import Any
import urllib.error
import urllib.parse
import urllib.request

from .config import ENABLED_ENV_VALUE, resolve_backend_api_url
from .output import emit_result, log


def _fetch_auth_env(
    workspace_id: str = "",
    auth_workspace_id: str = "",
    source_workspace_id: str = "",
) -> tuple[dict[str, Any], str | None, str | None, dict[str, Any]]:
    """Fetch auth env vars, model, and runtime ID from backend.

    Returns a tuple of (env_vars, model, runtime_id, auth_trace):
      env_vars: dict of env vars to inject into subprocess
      model: agent CLI model from system settings (or None for default)
      runtime_id: selected runtime ID for quota attribution (or None)
      auth_trace: backend selection trace metadata

    Falls back to host env vars if the backend is unreachable.
    Raises SystemExit with clear message if auth is configured but broken.
    """
    api_url = resolve_backend_api_url()
    if not api_url:
        return _env_fallback(), None, None, {}

    params = {}
    if workspace_id:
        params["workspace_id"] = workspace_id
    if auth_workspace_id:
        params["auth_workspace_id"] = auth_workspace_id
    if source_workspace_id:
        params["source_workspace_id"] = source_workspace_id

    url = f"{api_url.rstrip('/')}/api/v1/auth/cli-token"
    if params:
        url = f"{url}?{urllib.parse.urlencode(params)}"
    try:
        req = urllib.request.Request(url, method="GET")
        req.add_header("Accept", "application/json")
        with urllib.request.urlopen(req, timeout=5) as resp:
            data = json.loads(resp.read().decode())
            env_vars = data.get("env", {})
            api_model = data.get("model") or None
            runtime_id = data.get("selected_runtime_id") or None
            if env_vars:
                mode = data.get("auth_mode", "unknown")
                selection_reason = data.get("selection_reason")
                log(
                    f"Auth env injected (mode={mode}, model={api_model}, "
                    f"runtime_id={runtime_id}, selection_reason={selection_reason}, "
                    f"keys={list(env_vars.keys())})"
                )
                return env_vars, api_model, runtime_id, data
            auth_mode = data.get("auth_mode", "unknown")
            error = data.get("error", "no env vars returned")
            log(f"Backend auth returned empty: mode={auth_mode}, error={error}")
            fallback = _env_fallback()
            if fallback:
                return fallback, api_model, runtime_id, data
            _fail_auth(auth_mode, error)
    except urllib.error.URLError as e:
        log(f"Failed to fetch auth env: {e}")
        return _env_fallback(), None, None, {}
    except Exception as e:
        log(f"Auth env fetch error: {e}")
        return _env_fallback(), None, None, {}


def _env_fallback() -> dict[str, str]:
    """Build auth env from host environment variables as fallback."""
    api_key = os.environ.get("GEMINI_API_KEY", "")
    if api_key:
        log("Using GEMINI_API_KEY from host env (fallback)")
        return {"GEMINI_API_KEY": api_key}

    if os.environ.get("GOOGLE_GENAI_USE_VERTEXAI", "").lower() == ENABLED_ENV_VALUE:
        log("Using Vertex AI from host env (fallback)")
        return {
            "GOOGLE_GENAI_USE_VERTEXAI": ENABLED_ENV_VALUE,
            "GOOGLE_CLOUD_PROJECT": os.environ.get("GOOGLE_CLOUD_PROJECT", ""),
            "GOOGLE_CLOUD_LOCATION": os.environ.get(
                "GOOGLE_CLOUD_LOCATION", "us-central1"
            ),
        }

    gca_token = os.environ.get("GOOGLE_CLOUD_ACCESS_TOKEN", "")
    if (
        os.environ.get("GOOGLE_GENAI_USE_GCA", "").lower() == ENABLED_ENV_VALUE
        and gca_token
    ):
        log("Using GCA from host env (fallback)")
        return {
            "GOOGLE_GENAI_USE_GCA": ENABLED_ENV_VALUE,
            "GOOGLE_CLOUD_ACCESS_TOKEN": gca_token,
        }

    log("WARNING: No auth configuration found (no API key, no Vertex AI, no GCA)")
    return {}


def _report_quota_exhausted(runtime_id: str | None) -> None:
    """Report quota exhaustion for the given runtime to the backend."""
    if not runtime_id:
        return
    api_url = resolve_backend_api_url()
    if not api_url:
        return
    url = f"{api_url.rstrip('/')}/api/v1/gca-pool/{runtime_id}/quota-exhausted"
    try:
        req = urllib.request.Request(url, method="POST")
        req.add_header("Content-Type", "application/json")
        with urllib.request.urlopen(req, timeout=5):
            log(f"Reported quota exhaustion for runtime {runtime_id}")
    except Exception as e:
        log(f"Failed to report quota exhaustion for {runtime_id}: {e}")


def _fail_auth(auth_mode: str, error: str) -> None:
    """Fail the task immediately with a clear auth error message."""
    if "expired" in error.lower() or "refresh failed" in error.lower():
        msg = (
            f"Authentication failed ({auth_mode}): {error}. "
            f"Please re-authenticate via Web Console > Settings > CLI Agent Keys > "
            f"Google Account tab > Disconnect then Connect."
        )
    elif "no oauth" in error.lower() or "no idp" in error.lower():
        msg = (
            f"Authentication not configured ({auth_mode}): {error}. "
            f"Please connect via Web Console > Settings > CLI Agent Keys."
        )
    else:
        msg = f"Authentication error ({auth_mode}): {error}"
    emit_result("failed", error=msg)
    sys.exit(1)


def _fetch_agent_context() -> dict[str, Any]:
    """Fetch agent context from backend."""
    api_url = resolve_backend_api_url()
    if not api_url:
        return {}
    url = f"{api_url.rstrip('/')}/api/v1/auth/agent-context"
    try:
        req = urllib.request.Request(url, method="GET")
        req.add_header("Accept", "application/json")
        with urllib.request.urlopen(req, timeout=5) as resp:
            return json.loads(resp.read().decode())
    except Exception as e:
        log(f"Failed to fetch agent context: {e}")
        return {}


def _extract_auth_scope(auth_trace: dict | None) -> dict | None:
    """Return a compact auth-scope trace for backend persistence."""
    if not isinstance(auth_trace, dict):
        return None
    keys = (
        "requested_workspace_id",
        "effective_workspace_id",
        "auth_workspace_id",
        "source_workspace_id",
        "selection_reason",
        "selection_trace",
    )
    scope = {
        key: auth_trace.get(key) for key in keys if auth_trace.get(key) is not None
    }
    return scope or None
