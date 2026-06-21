import os
from pathlib import Path

try:
    import yaml  # noqa: F401

    HAS_YAML = True
except ImportError:
    HAS_YAML = False

try:
    import requests

    HAS_REQUESTS = True
except ImportError:
    requests = None
    HAS_REQUESTS = False

BASE_URL = os.getenv("BASE_URL", "http://localhost:8200")
OWNER_USER_ID = os.getenv("OWNER_USER_ID", "default-user")
LLM_MOCK = os.getenv("LLM_MOCK", "").lower() in ("true", "1", "yes")


def detect_capabilities_path() -> Path:
    env_path = os.getenv("CAPABILITIES_PATH")
    if env_path:
        return Path(env_path)
    if Path("/app/backend/app/capabilities").exists():
        return Path("/app/backend/app/capabilities")
    script_dir = Path(__file__).resolve().parents[1]
    return script_dir.parent / "backend" / "app" / "capabilities"


CAPABILITIES_PATH = detect_capabilities_path()
