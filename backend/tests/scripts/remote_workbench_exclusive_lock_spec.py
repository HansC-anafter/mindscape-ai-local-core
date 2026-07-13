from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from remote_workbench_authorization_cutover.exclusive_lock import phase06_runner_lock
from remote_workbench_authorization_cutover.io import CutoverError


def test_host_global_lock_rejects_second_process_and_releases(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    state = tmp_path / "state"
    monkeypatch.setenv("REMOTE_WORKBENCH_BRIDGE_STATE_DIR", str(state))
    script = """
from remote_workbench_authorization_cutover.exclusive_lock import phase06_runner_lock
from remote_workbench_authorization_cutover.io import CutoverError
try:
    with phase06_runner_lock():
        pass
except CutoverError:
    raise SystemExit(23)
""".strip()
    environment = dict(os.environ)
    environment["PYTHONPATH"] = str(REPO_ROOT / "scripts")

    with phase06_runner_lock() as lock_path:
        blocked = subprocess.run(
            [sys.executable, "-c", script],
            check=False,
            env=environment,
            capture_output=True,
            text=True,
            timeout=10,
        )
        assert blocked.returncode == 23
        assert blocked.stdout == ""
        assert blocked.stderr == ""
        assert lock_path.stat().st_mode & 0o777 == 0o600
        assert state.stat().st_mode & 0o777 == 0o700

    acquired = subprocess.run(
        [sys.executable, "-c", script],
        check=False,
        env=environment,
        capture_output=True,
        text=True,
        timeout=10,
    )
    assert acquired.returncode == 0


def test_host_global_lock_rejects_symlink_and_wrong_mode(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    target = tmp_path / "target"
    target.mkdir(mode=0o700)
    linked = tmp_path / "linked"
    linked.symlink_to(target, target_is_directory=True)
    monkeypatch.setenv("REMOTE_WORKBENCH_BRIDGE_STATE_DIR", str(linked))
    with pytest.raises(CutoverError, match="symbolic"):
        with phase06_runner_lock():
            pass

    state = tmp_path / "state"
    state.mkdir(mode=0o755)
    monkeypatch.setenv("REMOTE_WORKBENCH_BRIDGE_STATE_DIR", str(state))
    with pytest.raises(CutoverError, match="Invalid permissions"):
        with phase06_runner_lock():
            pass


def test_cli_holds_lock_before_repository_or_runtime_actions() -> None:
    source = (
        REPO_ROOT / "scripts/verify_remote_workbench_identity_workspace_authorization.py"
    ).read_text(encoding="utf-8")
    lock = source.index("with phase06_runner_lock():")
    dispatch = source.index("return _run_locked(args)", lock)
    interrupted_close = source.index("safe_close_before_preflight(", dispatch)
    repository = source.index("lock_phase06_repositories(", dispatch)
    workflow = source.index("workflow.cutover(", repository)

    assert lock < dispatch < interrupted_close < repository < workflow
