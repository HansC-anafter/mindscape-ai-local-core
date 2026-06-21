import os
import shutil

_gemini_cli_env = os.environ.get("GEMINI_CLI_PATH", "").strip()
if _gemini_cli_env:
    GEMINI_CLI = _gemini_cli_env
else:
    GEMINI_CLI = shutil.which("gemini") or "gemini"

GEMINI_CLI_MODEL = os.environ.get("GEMINI_CLI_MODEL", "gemini-3-pro")
MAX_OUTPUT = 100_000
ENABLED_ENV_VALUE = "true"

_bridge_backend_url = ""


def set_bridge_backend_url(api_url: str) -> None:
    """Store the dispatch payload backend URL for this process."""
    global _bridge_backend_url
    _bridge_backend_url = api_url or ""


def resolve_backend_api_url() -> str:
    """Return the payload backend URL or the host environment fallback."""
    return _bridge_backend_url or os.environ.get("MINDSCAPE_BACKEND_API_URL", "")
