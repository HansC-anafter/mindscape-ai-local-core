import json
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
SCRIPTS_DIR = REPO_ROOT / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import gemini_cli_runtime_bridge as public_bridge  # noqa: E402
from gemini_cli_runtime_bridge_core.auth import _extract_auth_scope  # noqa: E402
from gemini_cli_runtime_bridge_core.filesystem import (  # noqa: E402
    _diff_file_snapshots,
)
from gemini_cli_runtime_bridge_core.response import _extract_response  # noqa: E402


def test_public_facade_exports_runtime_bridge_contract() -> None:
    expected = (
        "GEMINI_CLI",
        "GEMINI_CLI_MODEL",
        "MAX_OUTPUT",
        "emit_result",
        "log",
        "main",
        "_diff_file_snapshots",
        "_env_fallback",
        "_extract_auth_scope",
        "_extract_response",
        "_fail_auth",
        "_fetch_agent_context",
        "_fetch_auth_env",
        "_looks_like_auth_error",
        "_looks_like_quota_error",
        "_report_quota_exhausted",
        "_resolve_host_sandbox_path",
        "_snapshot_files",
    )

    missing = [name for name in expected if not hasattr(public_bridge, name)]

    assert missing == []


def test_extract_response_summarizes_successful_tool_only_output() -> None:
    raw = json.dumps(
        {
            "response": "",
            "stats": {
                "tools": {
                    "totalCalls": 2,
                    "totalSuccess": 2,
                    "byName": {
                        "read_file": {"count": 1, "success": 1, "fail": 0},
                        "list_files": {"count": 1, "success": 1, "fail": 0},
                    },
                }
            },
        }
    )

    output, error = _extract_response(raw)

    assert error is None
    assert "Agent completed 2 tool call(s)" in output
    assert "- read_file: 1 calls (1 ok, 0 fail)" in output
    assert "- list_files: 1 calls (1 ok, 0 fail)" in output


def test_diff_file_snapshots_returns_sorted_created_and_modified() -> None:
    before = {
        "a.txt": (10, 5),
        "b.txt": (20, 8),
    }
    after = {
        "b.txt": (30, 8),
        "c.txt": (40, 3),
        "a.txt": (10, 5),
    }

    created, modified = _diff_file_snapshots(before, after)

    assert created == ["c.txt"]
    assert modified == ["b.txt"]


def test_extract_auth_scope_keeps_only_present_trace_fields() -> None:
    scope = _extract_auth_scope(
        {
            "requested_workspace_id": "ws_requested",
            "effective_workspace_id": "ws_effective",
            "auth_workspace_id": None,
            "selection_reason": "runtime_default",
            "unrelated": "ignored",
        }
    )

    assert scope == {
        "requested_workspace_id": "ws_requested",
        "effective_workspace_id": "ws_effective",
        "selection_reason": "runtime_default",
    }


def test_empty_payload_cli_smoke_returns_failed_json_without_runtime_call() -> None:
    script = SCRIPTS_DIR / "gemini_cli_runtime_bridge.py"

    result = subprocess.run(
        [sys.executable, str(script)],
        input="{}",
        capture_output=True,
        text=True,
        timeout=5,
        check=False,
    )

    payload = json.loads(result.stdout)

    assert result.returncode == 0
    assert payload["status"] == "failed"
    assert payload["error"] == "Empty task"
    assert result.stderr == ""
