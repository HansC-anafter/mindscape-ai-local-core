from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from remote_workbench_authorization_cutover.enrollment_checkpoint import (
    checkpoint_path,
    load_checkpoint,
    write_checkpoint,
)
from remote_workbench_authorization_cutover.io import CutoverError, write_private_json
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


LOCAL_COMMIT = "1" * 40
CLOUD_COMMIT = "2" * 40
INSTALL_ID = "3" * 32
MANIFEST_HASH = "4" * 64
CONFIG_HASH = "5" * 64
TUNNEL_ID = "11111111-2222-4333-8444-555555555555"


def _admins() -> list[dict[str, str]]:
    return [
        {
            "email": "hans@anafter.co",
            "subject": "subject-hans",
            "status": "active",
        },
        {
            "email": "pproo.reader@gmail.com",
            "subject": "subject-pproo",
            "status": "active",
        },
    ]


def _inputs(tmp_path: Path, *, outsider: bool) -> SecureInputs:
    paths: dict[str, Path] = {}
    claims: dict[str, dict] = {}
    rows = (
        ("hans", "hans@anafter.co", "subject-hans"),
        ("pproo", "pproo.reader@gmail.com", "subject-pproo"),
        ("outsider", "outsider@example.com", "subject-outsider"),
    )
    for label, email, subject in rows:
        if label == "outsider" and not outsider:
            continue
        path = tmp_path / f"{label}.jwt"
        path.write_text(f"secret-{label}-cookie", encoding="utf-8")
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
        policy={
            "expected_revision": 7,
            "access_issuer": EXPECTED_ISSUER,
            "access_audience": EXPECTED_AUDIENCE,
            "remote_access_state": "enforced",
            "local_core_super_admins": _admins(),
        },
        jwt_paths=paths,
        jwt_claims=claims,
        cloudflare_account_id="a" * 32,
        cloudflare_tunnel_id=TUNNEL_ID,
        cloudflare_api_token_path=tmp_path / "cloudflare-api-token.txt",
    )


def _initial_runtime() -> dict:
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


def _enrollment_runtime() -> dict:
    return {
        "id": "remote-workbench-runtime",
        "revision": 9,
        "access_issuer": EXPECTED_ISSUER,
        "access_audience": EXPECTED_AUDIENCE,
        "auth_config_fingerprint": EXPECTED_FINGERPRINT,
        "auth_config_source": "runtime_policy",
        "remote_access_state": "enrollment_only",
        "local_core_super_admins": _admins(),
        "source": "persisted_policy",
    }


def _install_job() -> dict:
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


def _ingress() -> dict:
    return {
        "tunnel_id": TUNNEL_ID,
        "config_version": 12,
        "config_sha256": CONFIG_HASH,
        "config_src": "cloudflare",
        "hostname": "remote-workbench.mindscapeai.app",
        "service": "http://mindscape-ai-local-core-frontend:3001",
        "catch_all": "http_status:404",
    }


def _effective() -> dict:
    return {
        "local_core_super_admins": _admins(),
        "effective_principals": [
            {
                "email": item["email"],
                "subject": item["subject"],
                "grant_sources": ["local_core_super_admin"],
            }
            for item in _admins()
        ],
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

    def apply_exact(self, _inputs: SecureInputs) -> dict:
        self.events.append("ingress-apply")
        return _ingress()

    def verify_exact(self, _inputs: SecureInputs, expected: dict) -> dict:
        self.events.append("ingress-verify")
        assert expected == _ingress()
        return expected


class Claims:
    def __init__(self, events: list[str]) -> None:
        self.events = events

    def pause_and_drain(self, _directory: Path, window: str) -> object:
        self.events.append(f"pause:{window}")
        return object()

    def verify_after(self, _before: object, _directory: Path, window: str) -> None:
        self.events.append(f"after:{window}")

    def resume(self) -> None:
        self.events.append("resume")


class Release:
    def __init__(self, events: list[str], *, source: dict[str, str] | None = None) -> None:
        self.events = events
        self.source = source or {
            "local_commit": LOCAL_COMMIT,
            "cloud_commit": CLOUD_COMMIT,
        }

    def require_no_active_install_jobs(self) -> None:
        self.events.append("idle")

    def verify_workspace_rows(self, _target: str, _inheritance: str) -> None:
        self.events.append("workspace-db")

    def verify_database_pools(self, _directory=None, label=None) -> None:
        self.events.append(f"db:{label or 'unlabeled'}")

    def verify_or_create_backup(self) -> Path:
        self.events.append("backup")
        return Path("/tmp/phase06-backup")

    def capture_known_good(self, _directory: Path) -> None:
        self.events.append("known-good")

    def package_current(self) -> Path:
        self.events.append("package")
        return Path("/tmp/current.mindpack")

    def install_current(self, _archive: Path, _directory: Path) -> dict:
        self.events.append("install")
        return _install_job()

    def verify_effective_policy_query_plan(self, _workspace_id: str) -> None:
        self.events.append("query-plan")

    def source_identity(self) -> dict[str, str]:
        self.events.append("source")
        return self.source

    def require_install_attempt_terminal(self, _directory: Path) -> dict:
        self.events.append("terminal")
        return _install_job()

    def verify_installed_runtime(self, _job: dict) -> None:
        self.events.append("installed-runtime")


class Runtime:
    def __init__(self, events: list[str]) -> None:
        self.events = events
        self.current = _initial_runtime()

    def activate_supervisor(self) -> None:
        self.events.append("activate")

    def verify_supervisor(self) -> dict:
        self.events.append("supervisor")
        return {"maintenance": True}

    def inspect_origin(self, _directory: Path, _workspace: str) -> dict:
        self.events.append("origin-inspect")
        return {"drift": {}}

    def verify_workspace_records(self, _target: str, _inheritance: str) -> None:
        self.events.append("workspace-api")

    def close_and_prove(self, _token: Path, _workspace: str) -> None:
        self.events.append("close-prove")

    def safe_close(self, reason: str) -> None:
        self.events.append(f"safe-close:{reason}")

    def get_effective_policy(self, _workspace: str) -> dict:
        self.events.append("effective")
        return _effective()

    def reconcile_origin(self, *_args, **_kwargs) -> None:
        raise AssertionError("unexpected origin reconciliation")

    def get_runtime_policy(self) -> dict:
        self.events.append("runtime")
        return dict(self.current)

    def assert_initial_seed(self, payload: dict, revision: int) -> None:
        assert payload == _initial_runtime()
        assert revision == 7

    def transition(self, body: dict, **_kwargs) -> dict:
        self.events.append(f"transition:{body['remote_access_state']}")
        self.current = {
            "id": "remote-workbench-runtime",
            "revision": body["expected_revision"] + 1,
            "access_issuer": body["access_issuer"],
            "access_audience": body["access_audience"],
            "auth_config_fingerprint": EXPECTED_FINGERPRINT,
            "auth_config_source": "runtime_policy",
            "remote_access_state": body["remote_access_state"],
            "local_core_super_admins": body["local_core_super_admins"],
            "source": "persisted_policy",
        }
        return dict(self.current)

    def verify_pending_coherence(self, _readback: dict, _workspace: str) -> None:
        self.events.append("pending-coherent")

    def reopen_transport(self) -> None:
        self.events.append("reopen")

    def verify_enrollment_assertions(self, _inputs: SecureInputs, _workspace: str) -> None:
        self.events.append("enrollment")

    def verify_effective_policies(self, *_args, **_kwargs) -> None:
        self.events.append("effective-verified")

    def assert_policy_readback(self, payload: dict, expected: dict) -> None:
        assert payload["access_issuer"] == expected["access_issuer"]
        assert payload["access_audience"] == expected["access_audience"]
        assert payload["local_core_super_admins"] == expected["local_core_super_admins"]

    def verify_gateway_latency(self, _inputs: SecureInputs, _workspace: str) -> None:
        self.events.append("latency")

    def verify_public_matrix(self, _inputs: SecureInputs, _workspace: str) -> None:
        self.events.append("public")

    def exit_maintenance(self) -> None:
        self.events.append("maintenance-exit")


def _workflow(events: list[str], release: Release | None = None) -> CutoverWorkflow:
    return CutoverWorkflow(
        edge=Edge(events),
        ingress=Ingress(events),
        release=release or Release(events),
        runtime=Runtime(events),
        resources=object(),
        claims=Claims(events),
    )


def _write_resume_checkpoint(tmp_path: Path) -> dict:
    checkpoint = write_checkpoint(
        tmp_path,
        target_workspace_id=EXPECTED_TARGET_WORKSPACE_ID,
        inheritance_workspace_id=EXPECTED_INHERITANCE_WORKSPACE_ID,
        runtime=_enrollment_runtime(),
        install=_install_job(),
        ingress=_ingress(),
        source={"local_commit": LOCAL_COMMIT, "cloud_commit": CLOUD_COMMIT},
        backup_dir=Path("/tmp/phase06-backup"),
    )
    write_private_json(tmp_path / "runtime-policy-before.json", _initial_runtime())
    return checkpoint


def _cutover(workflow: CutoverWorkflow, tmp_path: Path) -> dict:
    return workflow.cutover(
        secure_input_dir=tmp_path,
        target_workspace_id=EXPECTED_TARGET_WORKSPACE_ID,
        inheritance_workspace_id=EXPECTED_INHERITANCE_WORKSPACE_ID,
    )


def test_missing_outsider_writes_private_checkpoint_and_preserves_bootstrap(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    events: list[str] = []
    inputs = _inputs(tmp_path, outsider=False)
    monkeypatch.setattr(workflow_module, "load_secure_inputs", lambda _path: inputs)

    result = _cutover(_workflow(events), tmp_path)

    assert result["status"] == "pending_outsider"
    assert result["maintenance"] is True
    assert result["tunnel"] == "closed"
    assert events.count("install") == 1
    assert "transition:enforced" not in events
    path = checkpoint_path(tmp_path)
    assert path.stat().st_mode & 0o777 == 0o600
    checkpoint = load_checkpoint(tmp_path)
    assert checkpoint is not None
    assert checkpoint["runtime"]["local_core_super_admins"] == sorted(
        _admins(), key=lambda item: (item["email"], item["subject"])
    )
    assert "secret-hans-cookie" not in path.read_text(encoding="utf-8")


def test_resume_uses_zero_package_or_install_and_completes_enforcement(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    events: list[str] = []
    _write_resume_checkpoint(tmp_path)
    inputs = _inputs(tmp_path, outsider=True)
    monkeypatch.setattr(workflow_module, "load_secure_inputs", lambda _path: inputs)
    workflow = _workflow(events)
    workflow.runtime.current = _enrollment_runtime()

    result = _cutover(workflow, tmp_path)

    assert result["status"] == "succeeded"
    assert "package" not in events
    assert "install" not in events
    assert events.count("terminal") == 1
    assert "transition:enforced" in events
    assert events[-1] == "maintenance-exit"


def test_resume_source_mismatch_fails_closed_before_install_readback(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    events: list[str] = []
    _write_resume_checkpoint(tmp_path)
    inputs = _inputs(tmp_path, outsider=True)
    monkeypatch.setattr(workflow_module, "load_secure_inputs", lambda _path: inputs)
    release = Release(
        events,
        source={"local_commit": "9" * 40, "cloud_commit": CLOUD_COMMIT},
    )
    workflow = _workflow(events, release)
    workflow.runtime.current = _enrollment_runtime()

    with pytest.raises(CutoverError, match="source identity changed"):
        _cutover(workflow, tmp_path)

    assert "terminal" not in events
    assert "install" not in events
    assert events[0] == "safe-close:authorization_resume_preflight"
    assert events[-1] == "safe-close:authorization_resume_failed"
