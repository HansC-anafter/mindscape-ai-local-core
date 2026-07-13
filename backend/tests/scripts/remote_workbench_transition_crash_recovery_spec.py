from __future__ import annotations

import sys
import time
from pathlib import Path
from typing import Any

import pytest


REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from remote_workbench_authorization_cutover.enrollment_checkpoint import write_checkpoint
from remote_workbench_authorization_cutover.io import write_private_json
from remote_workbench_authorization_cutover.policy_receipt import record_policy_intent
from remote_workbench_authorization_cutover.secure_inputs import (
    EXPECTED_AUDIENCE,
    EXPECTED_FINGERPRINT,
    EXPECTED_INHERITANCE_WORKSPACE_ID,
    EXPECTED_ISSUER,
    EXPECTED_TARGET_WORKSPACE_ID,
    SecureInputs,
)
from remote_workbench_authorization_cutover.workflow import CutoverWorkflow
import remote_workbench_authorization_cutover.workflow as workflow_module


INSTALL_ID = "3" * 32
MANIFEST_HASH = "4" * 64
CONFIG_HASH = "5" * 64
LOCAL_COMMIT = "6" * 40
CLOUD_COMMIT = "7" * 40
TUNNEL_ID = "11111111-2222-4333-8444-555555555555"


def _admins() -> list[dict[str, str]]:
    return [
        {"email": "hans@anafter.co", "subject": "subject-hans", "status": "active"},
        {
            "email": "pproo.reader@gmail.com",
            "subject": "subject-pproo",
            "status": "active",
        },
    ]


def _initial() -> dict[str, Any]:
    return {
        "id": "remote-workbench-runtime",
        "revision": 7,
        "access_issuer": None,
        "access_audience": None,
        "auth_config_fingerprint": None,
        "auth_config_source": "runtime_policy",
        "remote_access_state": "enrollment_only",
        "local_core_super_admins": [],
        "source": "default_deny",
    }


def _policy_body(revision: int, state: str, admins: list[dict[str, str]]) -> dict:
    return {
        "expected_revision": revision,
        "access_issuer": EXPECTED_ISSUER,
        "access_audience": EXPECTED_AUDIENCE,
        "remote_access_state": state,
        "local_core_super_admins": admins,
    }


def _readback(body: dict[str, Any]) -> dict[str, Any]:
    nullable = body.get("access_issuer") is None
    return {
        "id": "remote-workbench-runtime",
        "revision": body["expected_revision"] + 1,
        "access_issuer": body.get("access_issuer"),
        "access_audience": body.get("access_audience"),
        "auth_config_fingerprint": None if nullable else EXPECTED_FINGERPRINT,
        "auth_config_source": "runtime_policy",
        "remote_access_state": body.get("remote_access_state"),
        "local_core_super_admins": body.get("local_core_super_admins", []),
        "source": "default_deny" if nullable else "persisted_policy",
    }


def _inputs(tmp_path: Path) -> SecureInputs:
    paths: dict[str, Path] = {}
    claims: dict[str, dict[str, Any]] = {}
    for label, email, subject in (
        ("hans", "hans@anafter.co", "subject-hans"),
        ("pproo", "pproo.reader@gmail.com", "subject-pproo"),
        ("outsider", "outsider@example.com", "subject-outsider"),
    ):
        path = tmp_path / f"{label}.jwt"
        path.write_text(f"cookie-{label}", encoding="utf-8")
        path.chmod(0o600)
        paths[label] = path
        claims[label] = {
            "iss": EXPECTED_ISSUER,
            "email": email,
            "sub": subject,
            "exp": int(time.time()) + 20_000,
        }
    return SecureInputs(
        directory=tmp_path,
        policy=_policy_body(7, "enforced", _admins()),
        jwt_paths=paths,
        jwt_claims=claims,
        cloudflare_account_id="a" * 32,
        cloudflare_tunnel_id=TUNNEL_ID,
        cloudflare_api_token_path=tmp_path / "cloudflare-api-token.txt",
    )


def _install_job() -> dict[str, Any]:
    return {
        "install_id": INSTALL_ID,
        "state": "succeeded",
        "source_kind": "file_upload",
        "result_payload": {
            "success": True,
            "capability_code": "mindscape_cloud_integration",
            "version": "1.0.0",
            "activation": {"manifest_hash": MANIFEST_HASH},
        },
    }


def _ingress() -> dict[str, Any]:
    return {
        "tunnel_id": TUNNEL_ID,
        "config_version": 12,
        "config_sha256": CONFIG_HASH,
        "config_src": "cloudflare",
        "hostname": "remote-workbench.mindscapeai.app",
        "service": "http://mindscape-ai-local-core-frontend:3001",
        "catch_all": "http_status:404",
    }


class Edge:
    def __init__(self, events: list[str]) -> None:
        self.events = events

    def verify(self) -> None:
        self.events.append("edge")


class Ingress:
    def __init__(self, events: list[str]) -> None:
        self.events = events

    def capture_prechange(self, _inputs: SecureInputs) -> None:
        self.events.append("ingress-read")

    def verify_exact(self, _inputs: SecureInputs, expected: dict) -> dict:
        self.events.append("ingress-verify")
        assert expected == _ingress()
        return expected


class Claims:
    def __init__(self, events: list[str]) -> None:
        self.events = events
        self.before = object()

    def pause_and_drain(self, _directory: Path, window: str) -> object:
        self.events.append(f"pause:{window}")
        return self.before

    def load_before(self, _directory: Path, window: str) -> object:
        self.events.append(f"load:{window}")
        return self.before

    def verify_after(self, before: object, _directory: Path, window: str) -> None:
        assert before is self.before
        self.events.append(f"after:{window}")

    def resume(self) -> None:
        self.events.append("claims-resume")


class Release:
    def __init__(self, events: list[str]) -> None:
        self.events = events
        self.install_calls = 0
        self.install_post_count = 0

    def require_no_active_install_jobs(self) -> None:
        self.events.append("idle")

    def verify_workspace_rows(self, *_args: str) -> None:
        self.events.append("workspace-db")

    def verify_database_pools(self, _directory: Path, label: str) -> None:
        self.events.append(f"db:{label}")

    def verify_or_create_backup(self) -> Path:
        self.events.append("backup")
        return Path("/tmp/phase06-backup")

    def capture_known_good(self, _directory: Path) -> None:
        self.events.append("known-good")

    def package_current(self) -> Path:
        self.events.append("package")
        return Path("/tmp/current.mindpack")

    def install_current(self, _archive: Path, _directory: Path) -> dict:
        self.install_calls += 1
        self.events.append("install-receipt-resume")
        return _install_job()

    def verify_effective_policy_query_plan(self, _workspace: str) -> None:
        self.events.append("query-plan")

    def source_identity(self) -> dict[str, str]:
        self.events.append("source")
        return {"local_commit": LOCAL_COMMIT, "cloud_commit": CLOUD_COMMIT}

    def require_install_attempt_terminal(self, _directory: Path) -> dict:
        self.events.append("install-terminal")
        return _install_job()

    def verify_installed_runtime(self, _job: dict) -> None:
        self.events.append("installed-runtime")


class Runtime:
    def __init__(self, events: list[str]) -> None:
        self.events = events
        self.current = _initial()
        self.tunnel_open = False
        self.stop_after_seed = False

    def crash_after_put(self, body: dict[str, Any], *, reopen: bool) -> None:
        self.current = _readback(body)
        self.tunnel_open = reopen
        self.events.append(f"process-kill:{body['remote_access_state']}")
        raise SystemExit("process-kill")

    def safe_close(self, reason: str) -> None:
        self.tunnel_open = False
        self.events.append(f"safe-close:{reason}:closed")

    def get_runtime_policy(self) -> dict[str, Any]:
        self.events.append("runtime-read")
        return dict(self.current)

    @staticmethod
    def policy_body(snapshot: dict[str, Any], revision: int) -> dict[str, Any]:
        return {
            "expected_revision": revision,
            "access_issuer": snapshot.get("access_issuer"),
            "access_audience": snapshot.get("access_audience"),
            "remote_access_state": snapshot.get("remote_access_state"),
            "local_core_super_admins": snapshot.get("local_core_super_admins", []),
        }

    def transition(self, body: dict[str, Any], **_kwargs: Any) -> dict[str, Any]:
        self.current = _readback(body)
        self.tunnel_open = bool(_kwargs.get("reopen"))
        self.events.append(f"transition:{body['remote_access_state']}")
        return dict(self.current)

    def activate_supervisor(self) -> None:
        self.events.append("activate")

    def verify_supervisor(self) -> dict[str, Any]:
        self.events.append("supervisor")
        return {"maintenance": True}

    def inspect_origin(self, *_args: Any) -> dict[str, Any]:
        self.events.append("origin-inspect")
        return {"drift": {}}

    def close_and_prove(self, *_args: Any) -> None:
        self.tunnel_open = False
        self.events.append("close-prove")

    def verify_workspace_records(self, *_args: str) -> None:
        self.events.append("workspace-api")

    def get_effective_policy(self, _workspace: str) -> dict[str, Any]:
        self.events.append("effective")
        return {
            "local_core_super_admins": _admins(),
            "effective_principals": _admins(),
        }

    def assert_initial_seed(self, payload: dict, revision: int) -> None:
        assert payload["remote_access_state"] == "enrollment_only"
        assert payload["access_issuer"] is None
        assert payload["revision"] == revision
        if self.stop_after_seed:
            raise SystemExit("stop-after-install")

    def assert_policy_readback(self, payload: dict, expected: dict) -> None:
        for key in (
            "access_issuer",
            "access_audience",
            "remote_access_state",
            "local_core_super_admins",
        ):
            assert payload[key] == expected[key]

    def verify_effective_policies(self, *_args: Any, **_kwargs: Any) -> None:
        self.events.append(f"effective-verified:{_kwargs['state']}")

    def resume_owned_transition(self, expected: dict, **_kwargs: Any) -> dict:
        self.close_and_prove()
        self.assert_policy_readback(self.current, expected)
        self.events.append("resume-owned-enforced")
        return dict(self.current)

    def reopen_transport(self) -> None:
        self.tunnel_open = True
        self.events.append("reopen")

    def verify_gateway_latency(self, *_args: Any) -> None:
        self.events.append("latency")

    def verify_public_matrix(self, *_args: Any) -> None:
        self.events.append("public")

    def exit_maintenance(self) -> None:
        self.events.append("maintenance-exit")


def _workflow(
    events: list[str], runtime: Runtime, release: Release, claims: Claims
) -> CutoverWorkflow:
    return CutoverWorkflow(
        edge=Edge(events),
        ingress=Ingress(events),
        release=release,
        runtime=runtime,
        resources=object(),
        claims=claims,
    )


def _cutover(workflow: CutoverWorkflow, tmp_path: Path) -> dict[str, Any]:
    return workflow.cutover(
        secure_input_dir=tmp_path,
        target_workspace_id=EXPECTED_TARGET_WORKSPACE_ID,
        inheritance_workspace_id=EXPECTED_INHERITANCE_WORKSPACE_ID,
    )


def test_pending_put_process_kill_fresh_workflow_restores_before_zero_post_install(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    events: list[str] = []
    inputs = _inputs(tmp_path)
    original = _initial()
    write_private_json(tmp_path / "runtime-policy-before.json", original)
    pending = _policy_body(
        7,
        "enrollment_only",
        [
            {
                "email": item["email"],
                "subject": "pending_identity_resolution",
                "status": "pending",
            }
            for item in _admins()
        ],
    )
    record_policy_intent(tmp_path, original=original, body=pending)
    runtime = Runtime(events)
    with pytest.raises(SystemExit, match="process-kill"):
        runtime.crash_after_put(pending, reopen=False)

    release = Release(events)
    runtime.stop_after_seed = True
    monkeypatch.setattr(workflow_module, "load_secure_inputs", lambda _path: inputs)
    fresh_start = len(events)
    with pytest.raises(SystemExit, match="stop-after-install"):
        _cutover(_workflow(events, runtime, release, Claims(events)), tmp_path)

    fresh_events = events[fresh_start:]
    assert fresh_events[0].startswith("safe-close:authorization_resume_preflight")
    assert fresh_events.index("transition:enrollment_only") < fresh_events.index("edge")
    assert release.install_calls == 1
    assert release.install_post_count == 0
    assert runtime.tunnel_open is False
    assert {
        key: runtime.current[key]
        for key in (
            "access_issuer",
            "access_audience",
            "remote_access_state",
            "local_core_super_admins",
        )
    } == {
        key: original[key]
        for key in (
            "access_issuer",
            "access_audience",
            "remote_access_state",
            "local_core_super_admins",
        )
    }


def test_enforced_reopen_process_kill_fresh_workflow_closes_then_resumes_checkpoint(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    events: list[str] = []
    inputs = _inputs(tmp_path)
    original = _initial()
    write_private_json(tmp_path / "runtime-policy-before.json", original)
    pending = _policy_body(7, "enrollment_only", [])
    enrollment = _policy_body(8, "enrollment_only", _admins())
    enforced = _policy_body(9, "enforced", _admins())
    for body in (pending, enrollment, enforced):
        record_policy_intent(tmp_path, original=original, body=body)
    enrollment_readback = _readback(enrollment)
    write_checkpoint(
        tmp_path,
        target_workspace_id=EXPECTED_TARGET_WORKSPACE_ID,
        inheritance_workspace_id=EXPECTED_INHERITANCE_WORKSPACE_ID,
        runtime=enrollment_readback,
        install=_install_job(),
        ingress=_ingress(),
        source={"local_commit": LOCAL_COMMIT, "cloud_commit": CLOUD_COMMIT},
        backup_dir=Path("/tmp/phase06-backup"),
    )
    runtime = Runtime(events)
    runtime.current = enrollment_readback
    with pytest.raises(SystemExit, match="process-kill"):
        runtime.crash_after_put(enforced, reopen=True)
    assert runtime.tunnel_open is True

    release = Release(events)
    monkeypatch.setattr(workflow_module, "load_secure_inputs", lambda _path: inputs)
    fresh_start = len(events)
    result = _cutover(_workflow(events, runtime, release, Claims(events)), tmp_path)

    fresh_events = events[fresh_start:]
    assert result["status"] == "succeeded"
    assert fresh_events[0].startswith("safe-close:authorization_resume_preflight")
    assert fresh_events.index("resume-owned-enforced") < fresh_events.index("reopen")
    assert fresh_events.index("public") < fresh_events.index("maintenance-exit")
    assert "install-receipt-resume" not in fresh_events
    assert release.install_post_count == 0
