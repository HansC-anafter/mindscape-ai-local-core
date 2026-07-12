from __future__ import annotations

import sys
import time
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from remote_workbench_authorization_cutover.install_state import AcceptedInstallError
from remote_workbench_authorization_cutover.io import CutoverError
from remote_workbench_authorization_cutover.secure_inputs import (
    EXPECTED_INHERITANCE_WORKSPACE_ID,
    EXPECTED_TARGET_WORKSPACE_ID,
    SecureInputs,
)
from remote_workbench_authorization_cutover.workflow import CutoverWorkflow
import remote_workbench_authorization_cutover.workflow as workflow_module


def _inputs(tmp_path: Path) -> SecureInputs:
    token = tmp_path / "hans.jwt"
    token.write_text("token", encoding="utf-8")
    token.chmod(0o600)
    claims = {"exp": int(time.time()) + 10_000}
    return SecureInputs(
        directory=tmp_path,
        policy={
            "expected_revision": 7,
            "local_core_super_admins": [],
        },
        jwt_paths={"hans": token},
        jwt_claims={"hans": claims},
    )


class Edge:
    def __init__(self, events: list[str]) -> None: self.events = events
    def verify(self) -> None: self.events.append("edge")


class Ingress:
    def __init__(self, events: list[str]) -> None: self.events = events
    def capture_prechange(self, _inputs) -> None: self.events.append("ingress-read")
    def apply_exact(self, _inputs) -> None: self.events.append("ingress-apply")


class Claims:
    def __init__(self, events: list[str]) -> None: self.events = events
    def pause_and_drain(self, _directory, window):
        self.events.append(f"pause:{window}")
        return object()
    def verify_after(self, _before, _directory, window): self.events.append(f"after:{window}")
    def resume(self): self.events.append("resume")


class Runtime:
    def __init__(self, events: list[str]) -> None: self.events = events
    def activate_supervisor(self): self.events.append("activate")
    def verify_supervisor(self): self.events.append("supervisor")
    def inspect_origin(self, _directory, _workspace):
        self.events.append("origin-inspect")
        return {"drift": {}}
    def verify_workspace_records(self, _target, _inheritance): self.events.append("workspace-api")
    def close_and_prove(self, _token, _workspace): self.events.append("close-prove")
    def get_effective_policy(self, _workspace):
        self.events.append("effective")
        return {}
    def safe_close(self, _reason): self.events.append("safe-close")


class Release:
    def __init__(
        self,
        events: list[str],
        *,
        package_error: Exception | None = None,
        install_error: AcceptedInstallError | None = None,
        idle_error: Exception | None = None,
        restore_job: dict | None = None,
    ) -> None:
        self.events = events
        self.package_error = package_error
        self.install_error = install_error
        self.idle_error = idle_error
        self.restore_job = restore_job

    def verify_or_create_backup(self):
        self.events.append("backup")
        return Path("/backup")
    def verify_database_pools(self): self.events.append("db")
    def verify_workspace_rows(self, _target, _inheritance): self.events.append("workspace-db")
    def require_no_active_install_jobs(self):
        self.events.append("idle")
        if self.idle_error: raise self.idle_error
    def capture_known_good(self, _directory): self.events.append("known-good")
    def package_current(self):
        self.events.append("package")
        if self.package_error: raise self.package_error
        return Path("/pack.mindpack")
    def install_current(self, _archive, _directory):
        self.events.append("install")
        if self.install_error: raise self.install_error
        return {"install_id": "1" * 32}
    def require_install_attempt_terminal(self, _directory): self.events.append("terminal")
    def require_restore_attempt_terminal(self, _directory):
        self.events.append("restore-terminal")
        return self.restore_job
    def verify_restore_job(self, _directory, _job): self.events.append("restore-verify")
    def restore_known_good(self, _directory): self.events.append("restore")


def _workflow(events: list[str], release: Release) -> CutoverWorkflow:
    return CutoverWorkflow(
        edge=Edge(events),
        ingress=Ingress(events),
        release=release,
        runtime=Runtime(events),
        resources=object(),
        claims=Claims(events),
    )


def _cutover(workflow: CutoverWorkflow, tmp_path: Path) -> None:
    workflow.cutover(
        secure_input_dir=tmp_path,
        target_workspace_id=EXPECTED_TARGET_WORKSPACE_ID,
        inheritance_workspace_id=EXPECTED_INHERITANCE_WORKSPACE_ID,
    )


def test_packaging_failure_never_starts_unnecessary_restore(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    events: list[str] = []
    monkeypatch.setattr(workflow_module, "load_secure_inputs", lambda _path: _inputs(tmp_path))
    with pytest.raises(CutoverError, match="package failed"):
        _cutover(_workflow(events, Release(events, package_error=CutoverError("package failed"))), tmp_path)
    assert "install" not in events
    assert "restore" not in events
    assert events[-1] == "safe-close"


def test_active_install_preflight_blocks_every_first_mutation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    events: list[str] = []
    monkeypatch.setattr(workflow_module, "load_secure_inputs", lambda _path: _inputs(tmp_path))
    release = Release(events, idle_error=CutoverError("active install"))
    with pytest.raises(CutoverError, match="active install"):
        _cutover(_workflow(events, release), tmp_path)
    assert events == ["edge", "ingress-read", "idle"]


def test_fresh_backup_is_created_only_after_durable_infra_pause(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    events: list[str] = []
    monkeypatch.setattr(workflow_module, "load_secure_inputs", lambda _path: _inputs(tmp_path))
    with pytest.raises(CutoverError, match="package failed"):
        _cutover(
            _workflow(events, Release(events, package_error=CutoverError("package failed"))),
            tmp_path,
        )

    pause = events.index("pause:06a-infra")
    backup = events.index("backup")
    activate = events.index("activate")
    close = events.index("close-prove")
    database = events.index("db")
    assert database < pause < backup < activate < close


def test_indeterminate_accepted_install_blocks_second_job(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    events: list[str] = []
    monkeypatch.setattr(workflow_module, "load_secure_inputs", lambda _path: _inputs(tmp_path))
    error = AcceptedInstallError(
        "poll timeout", install_id="2" * 32, state="running", terminal=False
    )
    with pytest.raises(CutoverError, match="Mandatory cutover backout"):
        _cutover(_workflow(events, Release(events, install_error=error)), tmp_path)
    assert "terminal" not in events
    assert "restore" not in events
    assert events[-1] == "safe-close"


def test_terminal_install_failure_gates_restore_on_job_idle_and_database(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    events: list[str] = []
    monkeypatch.setattr(workflow_module, "load_secure_inputs", lambda _path: _inputs(tmp_path))
    error = AcceptedInstallError(
        "job failed", install_id="3" * 32, state="failed", terminal=True
    )
    with pytest.raises(AcceptedInstallError):
        _cutover(_workflow(events, Release(events, install_error=error)), tmp_path)
    tail = events[events.index("safe-close"):]
    assert tail == [
        "safe-close",
        "pause:phase06-backout",
        "terminal",
        "idle",
        "db",
        "restore",
        "after:phase06-backout",
        "resume",
    ]


@pytest.mark.parametrize(("state", "last_event"), [("succeeded", "restore-verify"), ("failed", "restore")])
def test_existing_restore_receipt_is_consumed_before_zero_or_one_new_restore(
    tmp_path: Path,
    state: str,
    last_event: str,
) -> None:
    events: list[str] = []
    (tmp_path / "restore-attempt.json").write_text("{}", encoding="utf-8")
    release = Release(events, restore_job={"state": state})
    workflow = _workflow(events, release)

    prior = workflow._restore_preflight(tmp_path)
    workflow._finish_restore(tmp_path, prior)

    assert events[:3] == ["restore-terminal", "idle", "db"]
    assert events[-1] == last_event
    assert events.count("restore") == (0 if state == "succeeded" else 1)
