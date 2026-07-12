from __future__ import annotations

import sys
import time
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT / "scripts"))

import remote_workbench_authorization_cutover.backout_closure as closure_module
from remote_workbench_authorization_cutover.backout_closure import BackoutClosure
from remote_workbench_authorization_cutover.io import CutoverError
from remote_workbench_authorization_cutover.secure_inputs import SecureInputs


def _inputs(tmp_path: Path) -> SecureInputs:
    token = tmp_path / "hans.jwt"
    token.write_text("token", encoding="utf-8")
    token.chmod(0o600)
    return SecureInputs(
        directory=tmp_path,
        policy={},
        jwt_paths={"hans": token},
        jwt_claims={"hans": {"exp": int(time.time()) + 10_000}},
    )


class Claims:
    def __init__(self, events: list[str], failure: str | None = None) -> None:
        self.events = events
        self.failure = failure
        self.before = object()

    def pause_and_drain(self, _directory, window):
        self.events.append(f"pause:{window}")
        return self.before

    def verify_after(self, before, _directory, window):
        assert before is self.before
        self.events.append(f"resource-after:{window}")
        if self.failure == "resource":
            raise CutoverError("resource closure failed")

    def resume(self):
        self.events.append("resume")


class Runtime:
    def __init__(self, events: list[str], failure: str | None = None) -> None:
        self.events = events
        self.failure = failure

    def safe_close(self, _reason):
        self.events.append("safe-close")

    def recover_origin(self, _directory):
        self.events.append("origin-recover-incomplete")
        if self.failure == "origin":
            raise CutoverError("origin recovery failed")

    def get_runtime_policy(self):
        self.events.append("policy-read")
        return {"revision": 8}

    def policy_body(self, _snapshot, _revision):
        return {"expected_revision": 8}

    def transition(self, _body, **_kwargs):
        self.events.append("policy-rollback")
        if self.failure == "policy":
            raise CutoverError("policy rollback failed")


class Release:
    def __init__(self, events: list[str], failure: str | None = None) -> None:
        self.events = events
        self.failure = failure

    def require_install_attempt_terminal(self, _directory):
        self.events.append("install-terminal")

    def require_restore_attempt_terminal(self, _directory):
        self.events.append("restore-terminal")
        return None

    def require_no_active_install_jobs(self):
        self.events.append("install-idle")

    def verify_restore_job(self, _directory, _job):
        self.events.append("restore-verify")

    def restore_known_good(self, _directory):
        self.events.append("pack-restore")
        if self.failure == "restore":
            raise CutoverError("pack restore failed")

    def verify_database_pools(self, _directory, label):
        self.events.append(f"database:{label}")
        if self.failure == "database":
            raise CutoverError("database closure failed")


def _closure(
    events: list[str],
    *,
    failure: str | None = None,
) -> tuple[BackoutClosure, Claims]:
    claims = Claims(events, failure)
    return (
        BackoutClosure(
            release=Release(events, failure),
            runtime=Runtime(events, failure),
            claims=claims,
        ),
        claims,
    )


@pytest.mark.parametrize("failure", ["origin", "policy", "restore", "database", "resource"])
def test_backout_failure_matrix_never_resumes_durable_claims(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    failure: str,
) -> None:
    events: list[str] = []
    closure, _claims = _closure(events, failure=failure)
    monkeypatch.setattr(
        closure_module,
        "current_policy_requires_rollback",
        lambda *_args, **_kwargs: True,
    )

    with pytest.raises(CutoverError):
        closure.close(
            inputs=_inputs(tmp_path),
            target_workspace_id="workspace-a",
            original={"revision": 7},
            rollback_policy=failure == "policy",
            restore_pack=failure == "restore",
            pack_restore_allowed=True,
            claims_paused=False,
            resource_before=None,
            resource_window=None,
            evidence_label="mandatory-backout",
            close_reason="test-backout",
        )

    assert events[0] == "pause:phase06-backout"
    assert "resume" not in events


@pytest.mark.parametrize("label", ["mandatory-backout", "explicit-backout"])
def test_incomplete_origin_receipt_recovers_first_and_resume_is_terminal(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    label: str,
) -> None:
    events: list[str] = []
    closure, _claims = _closure(events)
    monkeypatch.setattr(
        closure_module,
        "current_policy_requires_rollback",
        lambda *_args, **_kwargs: True,
    )

    closure.close(
        inputs=_inputs(tmp_path),
        target_workspace_id="workspace-a",
        original={"revision": 7},
        rollback_policy=True,
        restore_pack=True,
        pack_restore_allowed=True,
        claims_paused=False,
        resource_before=None,
        resource_window=None,
        evidence_label=label,
        close_reason="test-backout",
    )

    origin = events.index("origin-recover-incomplete")
    assert origin < events.index("policy-read") < events.index("install-terminal")
    assert events[-3:] == [
        f"database:{label}",
        "resource-after:phase06-backout",
        "resume",
    ]
