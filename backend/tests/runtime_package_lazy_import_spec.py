import json
import os
import subprocess
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]


def _run_probe(source: str) -> dict:
    env = os.environ.copy()
    env["PYTHONPATH"] = f"{REPO_ROOT}:{REPO_ROOT / 'backend'}"
    result = subprocess.run(
        [sys.executable, "-c", source],
        cwd=REPO_ROOT,
        env=env,
        check=True,
        capture_output=True,
        text=True,
    )
    return json.loads(result.stdout)


def test_runtime_package_import_does_not_eager_load_agent_executor_or_vertex():
    data = _run_probe(
        """
import json
import sys
import backend.app.services.runtime as runtime

print(json.dumps({
    "has_all": "LangChainAgentExecutor" in runtime.__all__,
    "agent_executor_loaded": "backend.app.services.runtime.agent_executor" in sys.modules,
    "langchain_loaded": any(name.startswith("langchain") for name in sys.modules),
    "vertex_loaded": any(
        name.startswith("google.cloud.aiplatform")
        or name.startswith("langchain_google_vertexai")
        for name in sys.modules
    ),
}))
"""
    )

    assert data == {
        "has_all": True,
        "agent_executor_loaded": False,
        "langchain_loaded": False,
        "vertex_loaded": False,
    }


def test_runtime_package_preserves_lazy_agent_executor_export():
    data = _run_probe(
        """
import json
import sys
from backend.app.services.runtime import LangChainAgentExecutor

print(json.dumps({
    "name": LangChainAgentExecutor.__name__,
    "agent_executor_loaded": "backend.app.services.runtime.agent_executor" in sys.modules,
}))
"""
    )

    assert data == {
        "name": "LangChainAgentExecutor",
        "agent_executor_loaded": True,
    }
