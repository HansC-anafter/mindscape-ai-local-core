from __future__ import annotations

import base64
import hashlib
import json
import sys
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from remote_workbench_authorization_cutover.io import CutoverError
from remote_workbench_authorization_cutover.install_state import AcceptedInstallError
from remote_workbench_authorization_cutover.install_receipt import next_restore_attempt_round
from remote_workbench_authorization_cutover.install_attempt_state import (
    write_install_attempt,
    write_install_intent,
)
from remote_workbench_authorization_cutover.http import HttpResponse
from remote_workbench_authorization_cutover.release import ReleaseGate


POOL_CSV = """database,user,cl_active,cl_waiting,sv_active,sv_idle,maxwait
mindscape_core,mindscape,1,0,3,7,0
mindscape_vectors,mindscape,0,0,1,4,0
"""
MANIFEST_HASH = "a" * 64
INSTALL_ID = "1" * 32
TARGET = "bac7ce63-e768-454d-96f3-3a00e8e1df69"
INHERITANCE = "e81713b4-385e-4755-96d5-1ceca4ec9e99"


class SequenceExecutor:
    def __init__(self, responses: list[str]) -> None:
        self.responses = list(responses)
        self.calls: list[list[str]] = []

    def run(self, args, *, timeout_seconds=60.0, input_text=None) -> str:
        self.calls.append(list(args))
        return self.responses.pop(0)


def _gate(executor: SequenceExecutor) -> ReleaseGate:
    return ReleaseGate(
        repo_root=REPO_ROOT,
        cloud_worktree=REPO_ROOT,
        executor=executor,
        http=object(),
        sleep=lambda _seconds: None,
    )


def test_database_gate_requires_recovery_transaction_and_default_read_only_off() -> None:
    executor = SequenceExecutor(["f|off|off\n", POOL_CSV])

    _gate(executor).verify_database_pools()

    postgres_query = executor.calls[0][-1]
    assert "pg_is_in_recovery" in postgres_query
    assert "transaction_read_only" in postgres_query
    assert "default_transaction_read_only" in postgres_query


def test_database_gate_rejects_default_read_only_or_pgbouncer_waiter() -> None:
    with pytest.raises(CutoverError, match="not writable"):
        _gate(SequenceExecutor(["f|off|on\n"])).verify_database_pools()

    waiting = POOL_CSV.replace("mindscape_core,mindscape,1,0", "mindscape_core,mindscape,1,1")
    with pytest.raises(CutoverError, match="waiting clients"):
        _gate(SequenceExecutor(["f|off|off\n", waiting])).verify_database_pools()

    missing_core = POOL_CSV.replace("mindscape_core", "other_core")
    with pytest.raises(CutoverError, match="mindscape_core pool is missing"):
        _gate(SequenceExecutor(["f|off|off\n", missing_core])).verify_database_pools()

    over_budget = POOL_CSV.replace("mindscape_core,mindscape,1,0,3,7", "mindscape_core,mindscape,1,0,21,20")
    with pytest.raises(CutoverError, match="connection budget"):
        _gate(SequenceExecutor(["f|off|off\n", over_budget])).verify_database_pools()


def test_workspace_rows_gate_requires_both_real_rows_and_no_inheritance_policy() -> None:
    payload = {
        "workspace_ids": sorted([TARGET, INHERITANCE]),
        "inheritance_policy_rows": 0,
    }
    executor = SequenceExecutor([json.dumps(payload)])
    _gate(executor).verify_workspace_rows(TARGET, INHERITANCE)
    sql = executor.calls[0][-1]
    assert "FROM workspaces" in sql
    assert "workspace_mobile_workbench_gateway_policies" in sql

    payload["inheritance_policy_rows"] = 1
    with pytest.raises(CutoverError, match="default-deny"):
        _gate(SequenceExecutor([json.dumps(payload)])).verify_workspace_rows(
            TARGET,
            INHERITANCE,
        )


def _plan(workspace_node: dict, *, index_exists: str = "t") -> str:
    payload = [
        {
            "Execution Time": 1.25,
            "Plan": {
                "Node Type": "Nested Loop Left Join",
                "Plans": [
                    {
                        "Node Type": "Index Scan",
                        "Relation Name": "remote_workbench_runtime_access_policies",
                    },
                    workspace_node,
                ],
            }
        }
    ]
    return f"{index_exists}\n{json.dumps(payload)}\n"


def test_effective_policy_query_plan_requires_single_session_workspace_index() -> None:
    executor = SequenceExecutor(
        [
            _plan(
                {
                    "Node Type": "Index Scan",
                    "Relation Name": "workspace_mobile_workbench_gateway_policies",
                }
            )
        ]
    )

    _gate(executor).verify_effective_policy_query_plan(
        "bac7ce63-e768-454d-96f3-3a00e8e1df69"
    )

    sql = executor.calls[0][-1]
    assert "BEGIN;" in sql
    assert "enable_seqscan" not in sql
    assert "pg_indexes" in sql
    assert "EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON)" in sql
    assert "LEFT JOIN workspace_mobile_workbench_gateway_policies" in sql
    assert "ROLLBACK;" in sql


def test_effective_policy_query_plan_accepts_bounded_tiny_scan_and_rejects_unbounded() -> None:
    index_node = {
        "Node Type": "Index Scan",
        "Relation Name": "workspace_mobile_workbench_gateway_policies",
    }
    with pytest.raises(CutoverError, match="index evidence"):
        _gate(SequenceExecutor([_plan(index_node, index_exists="f")])).verify_effective_policy_query_plan(
            "bac7ce63-e768-454d-96f3-3a00e8e1df69"
        )

    bounded_seq = {
        "Node Type": "Seq Scan",
        "Relation Name": "workspace_mobile_workbench_gateway_policies",
        "Plan Rows": 16,
        "Actual Rows": 1,
        "Rows Removed by Filter": 15,
        "Shared Hit Blocks": 2,
        "Shared Read Blocks": 0,
    }
    _gate(SequenceExecutor([_plan(bounded_seq)])).verify_effective_policy_query_plan(
        "bac7ce63-e768-454d-96f3-3a00e8e1df69"
    )
    unbounded_seq = {**bounded_seq, "Plan Rows": 33}
    with pytest.raises(CutoverError, match="unbounded workspace scan"):
        _gate(SequenceExecutor([_plan(unbounded_seq)])).verify_effective_policy_query_plan(
            "bac7ce63-e768-454d-96f3-3a00e8e1df69"
        )

    wrong_relation = {"Node Type": "Index Scan", "Relation Name": "other_table"}
    with pytest.raises(CutoverError, match="scan the workspace policy once"):
        _gate(SequenceExecutor([_plan(wrong_relation)])).verify_effective_policy_query_plan(
            "bac7ce63-e768-454d-96f3-3a00e8e1df69"
        )


class InstalledHttp:
    def __init__(self, *, asset_body: bytes = b"export default 1;", version: str = "1.2.3") -> None:
        self.asset_body = asset_body
        self.version = version
        self.integrity = "sha256-" + base64.b64encode(
            hashlib.sha256(asset_body).digest()
        ).decode("ascii")
        self.requests: list[tuple[str, dict]] = []

    def get_json(self, url, *, timeout_seconds=5.0) -> dict:
        if url.endswith("/installed-capabilities/mindscape_cloud_integration"):
            return {
                "id": "mindscape_cloud_integration",
                "code": "mindscape_cloud_integration",
                "version": self.version,
            }
        return {
            "pack_id": "mindscape_cloud_integration",
            "enabled": True,
            "activation_state": "active",
            "manifest_hash": MANIFEST_HASH,
        }

    def request(self, method, url, **kwargs) -> HttpResponse:
        self.requests.append((url, kwargs))
        if url.endswith("/ui-components"):
            components = [
                {
                    "code": "GlobalAdministrators",
                    "asset_url": (
                        "/api/v1/capability-packs/installed-capabilities/"
                        "mindscape_cloud_integration/ui-assets/1.2.3/components/admin.mjs"
                    ),
                    "integrity": self.integrity,
                    "bytes": len(self.asset_body),
                    "runtime": "mindscape-react-bridge-v1",
                }
            ]
            return HttpResponse(200, {}, json.dumps(components).encode("utf-8"))
        return HttpResponse(200, {}, self.asset_body)


class CompletedInstallHttp:
    def __init__(self, directory: Path) -> None:
        self.directory = directory

    def get_json(self, _url, **_kwargs) -> dict:
        intent = json.loads(
            (self.directory / "install-intent.json").read_text(encoding="utf-8")
        )
        return {
            "install_id": INSTALL_ID,
            "state": "succeeded",
            "source_kind": "file_upload",
            "source_payload": {
                "filename": intent["multipart_filename"],
                "mindpack_path": (
                    f"/app/data/capability-install-jobs/{INSTALL_ID}/input.mindpack"
                ),
            },
            "result_payload": {"execution_activation": {"state": "active"}},
        }


class InstallStateHttp:
    def __init__(self, state: str, directory: Path, *, kind: str = "install") -> None:
        self.state = state
        self.directory = directory
        self.kind = kind
        self.urls: list[str] = []

    def get_json(self, url, **_kwargs) -> dict:
        self.urls.append(url)
        install_id = url.rsplit("/", 1)[-1]
        intent = json.loads(
            (self.directory / f"{self.kind}-intent.json").read_text(encoding="utf-8")
        )
        return {
            "install_id": install_id,
            "state": self.state,
            "source_kind": "file_upload",
            "source_payload": {
                "filename": intent["multipart_filename"],
                "mindpack_path": (
                    f"/app/data/capability-install-jobs/{install_id}/input.mindpack"
                ),
            },
        }


def test_package_gate_uses_the_current_verified_python_runtime(tmp_path: Path) -> None:
    install_id = INSTALL_ID
    executor = SequenceExecutor(
        [
            "",
            "",
            (
                "mindscape_cloud_integration/manifest.yaml\n"
                "mindscape_cloud_integration/ui_dist/ui_dist_manifest.json\n"
            ),
            "0",
            "f|off|off",
            POOL_CSV,
            json.dumps(
                {
                    "success": True,
                    "accepted": True,
                    "install_id": install_id,
                    "state": "queued",
                    "status_url": f"/api/v1/capability-packs/install-jobs/{install_id}",
                }
            ),
        ]
    )
    gate = ReleaseGate(
        repo_root=REPO_ROOT,
        cloud_worktree=tmp_path,
        executor=executor,
        http=CompletedInstallHttp(tmp_path),
        sleep=lambda _seconds: None,
    )
    gate.pack.verify_installed_runtime = lambda _job: None

    archive = gate.package_current()
    archive.write_bytes(b"pack")
    gate.install_current(archive, tmp_path)

    assert executor.calls[0][0] == sys.executable
    assert executor.calls[1][0] == sys.executable
    assert executor.calls[0][1].endswith("scripts/validate_manifest.py")
    assert executor.calls[1][1].endswith("scripts/package_capability.py")


@pytest.mark.parametrize(("state", "terminal"), [("failed", True), ("queued", False)])
def test_accepted_install_error_tracks_exact_terminal_or_indeterminate_state(
    tmp_path: Path,
    state: str,
    terminal: bool,
) -> None:
    install_id = "2" * 32
    archive = tmp_path / "current.mindpack"
    archive.write_bytes(b"pack")
    executor = SequenceExecutor(
        [
            "0",
            "f|off|off",
            POOL_CSV,
            json.dumps(
                {
                    "success": True,
                    "accepted": True,
                    "install_id": install_id,
                    "state": "queued",
                    "status_url": f"/api/v1/capability-packs/install-jobs/{install_id}",
                }
            )
        ]
    )
    times = iter([0.0, 1.0] if terminal else [0.0, 601.0])
    gate = ReleaseGate(
        repo_root=REPO_ROOT,
        cloud_worktree=REPO_ROOT,
        executor=executor,
        http=InstallStateHttp(state, tmp_path),
        sleep=lambda _seconds: None,
        monotonic=lambda: next(times),
    )

    with pytest.raises(AcceptedInstallError) as captured:
        gate.install_current(archive, tmp_path)

    assert captured.value.install_id == install_id
    assert captured.value.terminal is terminal
    receipt = json.loads((tmp_path / "install-attempt.json").read_text(encoding="utf-8"))
    assert receipt["install_id"] == install_id
    assert receipt["terminal"] is terminal
    assert receipt["archive_sha256"] == hashlib.sha256(b"pack").hexdigest()
    assert (tmp_path / "install-intent.json").stat().st_mode & 0o777 == 0o600


def test_restore_preflight_refreshes_exact_job_and_blocks_active_attempt(tmp_path: Path) -> None:
    install_id = "3" * 32
    intent = write_install_intent(
        tmp_path,
        attempt_kind="install",
        attempt_round=1,
        archive_sha256="a" * 64,
        multipart_filename=f"remote-workbench-install-{'a' * 32}.mindpack",
    )
    write_install_attempt(
        tmp_path,
        intent=intent,
        install_id=install_id,
        state="queued",
        terminal=False,
    )
    active_http = InstallStateHttp("running", tmp_path)
    active = ReleaseGate(
        repo_root=REPO_ROOT,
        cloud_worktree=REPO_ROOT,
        executor=SequenceExecutor([]),
        http=active_http,
    )
    with pytest.raises(CutoverError, match="maintenance is required"):
        active.require_install_attempt_terminal(tmp_path)
    assert active_http.urls == [
        f"http://localhost:8220/api/v1/capability-packs/install-jobs/{install_id}"
    ]

    terminal = ReleaseGate(
        repo_root=REPO_ROOT,
        cloud_worktree=REPO_ROOT,
        executor=SequenceExecutor([]),
        http=InstallStateHttp("succeeded", tmp_path),
    )
    assert terminal.require_install_attempt_terminal(tmp_path)["state"] == "succeeded"


def test_failed_restore_receipt_allows_exactly_the_next_round(tmp_path: Path) -> None:
    intent = write_install_intent(
        tmp_path,
        attempt_kind="restore",
        attempt_round=2,
        archive_sha256="b" * 64,
        multipart_filename=f"remote-workbench-restore-{'b' * 32}.mindpack",
    )
    write_install_attempt(
        tmp_path,
        intent=intent,
        install_id="4" * 32,
        state="failed",
        terminal=True,
    )
    assert next_restore_attempt_round(tmp_path) == 3

    receipt = tmp_path / "restore-attempt.json"
    payload = json.loads(receipt.read_text(encoding="utf-8"))
    payload["state"] = "succeeded"
    receipt.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(CutoverError, match="new restore round"):
        next_restore_attempt_round(tmp_path)


def _install_job(*, source_kind: str = "file_upload") -> dict:
    return {
        "source_kind": source_kind,
        "result_payload": {
            "success": True,
            "capability_code": "mindscape_cloud_integration",
            "version": "1.2.3",
            "activation": {"manifest_hash": MANIFEST_HASH},
        },
    }


def test_installed_runtime_gate_verifies_source_version_activation_and_asset_bytes() -> None:
    http = InstalledHttp()
    gate = ReleaseGate(
        repo_root=REPO_ROOT,
        cloud_worktree=REPO_ROOT,
        executor=SequenceExecutor([]),
        http=http,
    )

    gate.verify_installed_runtime(_install_job())
    assert http.requests[0][1]["max_response_bytes"] == 262_144
    assert http.requests[1][1]["max_response_bytes"] == len(http.asset_body)


def test_installed_runtime_gate_rejects_wrong_source_or_asset_integrity() -> None:
    gate = ReleaseGate(
        repo_root=REPO_ROOT,
        cloud_worktree=REPO_ROOT,
        executor=SequenceExecutor([]),
        http=InstalledHttp(),
    )
    with pytest.raises(CutoverError, match="source metadata"):
        gate.verify_installed_runtime(_install_job(source_kind="cloud_provider_pack"))

    corrupted = InstalledHttp()
    corrupted.integrity = "sha256-invalid"
    bad_gate = ReleaseGate(
        repo_root=REPO_ROOT,
        cloud_worktree=REPO_ROOT,
        executor=SequenceExecutor([]),
        http=corrupted,
    )
    with pytest.raises(CutoverError, match="integrity verification"):
        bad_gate.verify_installed_runtime(_install_job())
