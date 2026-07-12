from __future__ import annotations

import hashlib
import json
import sys
import tarfile
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from remote_workbench_authorization_cutover.install_attempt_state import (
    load_install_attempt,
    load_install_intent,
    write_install_attempt,
    write_install_intent,
)
from remote_workbench_authorization_cutover.install_receipt import InstallReceiptGate
from remote_workbench_authorization_cutover.install_state import (
    ActiveInstallAttemptError,
)
from remote_workbench_authorization_cutover.io import CutoverError, write_private_json
from remote_workbench_authorization_cutover.pack_release import PackReleaseGate


def _job(install_id: str, filename: str, state: str) -> dict:
    payload = {
        "install_id": install_id,
        "source_kind": "file_upload",
        "state": state,
        "source_payload": {
            "filename": filename,
            "mindpack_path": (
                f"/app/data/capability-install-jobs/{install_id}/input.mindpack"
            ),
        },
    }
    if state == "succeeded":
        payload["result_payload"] = {
            "execution_activation": {"state": "activated"}
        }
    return payload


class DynamicStatusHttp:
    def __init__(
        self,
        directory: Path,
        state: str | list[str] = "succeeded",
    ) -> None:
        self.directory = directory
        self.states = [state] if isinstance(state, str) else list(state)
        self.calls = 0

    def get_json(self, url: str, **_kwargs) -> dict:
        self.calls += 1
        install_id = url.rsplit("/", 1)[-1]
        kind = "restore" if (self.directory / "restore-intent.json").exists() else "install"
        intent = load_install_intent(self.directory, attempt_kind=kind)
        assert intent is not None
        state = self.states.pop(0) if len(self.states) > 1 else self.states[0]
        return _job(install_id, intent["multipart_filename"], state)


class IntakeExecutor:
    def __init__(
        self,
        directory: Path,
        *,
        install_id: str,
        lose_response: bool = False,
        recovery_count: int = 1,
    ) -> None:
        self.directory = directory
        self.install_id = install_id
        self.lose_response = lose_response
        self.recovery_count = recovery_count
        self.calls: list[list[str]] = []

    def run(self, args, **_kwargs) -> str:
        command = list(args)
        self.calls.append(command)
        if command[0] == "curl":
            assert (self.directory / "install-intent.json").exists()
            if self.lose_response:
                raise CutoverError("response lost")
            return json.dumps(
                {
                    "success": True,
                    "accepted": True,
                    "install_id": self.install_id,
                    "state": "queued",
                    "status_url": (
                        "/api/v1/capability-packs/install-jobs/" + self.install_id
                    ),
                }
            )
        intent = load_install_intent(self.directory, attempt_kind="install")
        assert intent is not None
        matches = [
            _job(self.install_id, intent["multipart_filename"], "queued")
            for _index in range(self.recovery_count)
        ]
        return json.dumps(matches)


def _archive(tmp_path: Path, content: bytes = b"pack") -> Path:
    path = tmp_path / "current.mindpack"
    path.write_bytes(content)
    return path


def _intent_and_receipt(tmp_path: Path, *, state: str) -> None:
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
        install_id="1" * 32,
        state=state,
        terminal=state in {"succeeded", "failed"},
    )


def test_response_loss_recovers_one_job_by_private_intent(tmp_path: Path) -> None:
    executor = IntakeExecutor(
        tmp_path,
        install_id="2" * 32,
        lose_response=True,
    )
    http = DynamicStatusHttp(tmp_path)
    gate = InstallReceiptGate(executor=executor, http=http, sleep=lambda _value: None)

    result = gate.resume_or_create(
        _archive(tmp_path),
        tmp_path,
        attempt_kind="install",
        overwrite=False,
        before_create=lambda: None,
        verify_succeeded=lambda _job: None,
    )

    assert result["install_id"] == "2" * 32
    assert [call[0] for call in executor.calls] == ["curl", "docker"]
    assert load_install_attempt(tmp_path, attempt_kind="install")["state"] == "succeeded"


def test_succeeded_and_active_reruns_never_post(tmp_path: Path) -> None:
    _intent_and_receipt(tmp_path, state="succeeded")
    executor = IntakeExecutor(tmp_path, install_id="1" * 32)
    before: list[str] = []
    gate = InstallReceiptGate(
        executor=executor,
        http=DynamicStatusHttp(tmp_path, "succeeded"),
    )
    gate.resume_or_create(
        _archive(tmp_path),
        tmp_path,
        attempt_kind="install",
        overwrite=False,
        before_create=lambda: before.append("create"),
        verify_succeeded=lambda _job: None,
    )
    assert executor.calls == []
    assert before == []

    receipt = load_install_attempt(tmp_path, attempt_kind="install")
    assert receipt is not None
    write_install_attempt(
        tmp_path,
        intent=load_install_intent(tmp_path, attempt_kind="install"),
        install_id=receipt["install_id"],
        state="queued",
        terminal=False,
    )
    with pytest.raises(ActiveInstallAttemptError, match="maintenance"):
        InstallReceiptGate(
            executor=executor,
            http=DynamicStatusHttp(tmp_path, "running"),
        ).resume_or_create(
            _archive(tmp_path),
            tmp_path,
            attempt_kind="install",
            overwrite=False,
            before_create=lambda: before.append("create"),
            verify_succeeded=lambda _job: None,
        )
    assert executor.calls == []
    assert before == []


def test_failed_rerun_opens_one_new_round_after_gate(tmp_path: Path) -> None:
    _intent_and_receipt(tmp_path, state="failed")
    executor = IntakeExecutor(tmp_path, install_id="3" * 32)
    before: list[str] = []
    gate = InstallReceiptGate(
        executor=executor,
        http=DynamicStatusHttp(tmp_path, ["failed", "succeeded"]),
    )
    gate.resume_or_create(
        _archive(tmp_path, b"next"),
        tmp_path,
        attempt_kind="install",
        overwrite=False,
        before_create=lambda: before.append("gated"),
        verify_succeeded=lambda _job: None,
    )
    intent = load_install_intent(tmp_path, attempt_kind="install")
    assert intent is not None and intent["attempt_round"] == 2
    assert intent["archive_sha256"] == hashlib.sha256(b"next").hexdigest()
    assert before == ["gated"]
    assert sum(call[0] == "curl" for call in executor.calls) == 1


@pytest.mark.parametrize("count", [0, 2])
def test_missing_or_ambiguous_intent_recovery_fails_closed(
    tmp_path: Path,
    count: int,
) -> None:
    write_install_intent(
        tmp_path,
        attempt_kind="install",
        attempt_round=1,
        archive_sha256="a" * 64,
        multipart_filename=f"remote-workbench-install-{'a' * 32}.mindpack",
    )
    executor = IntakeExecutor(
        tmp_path,
        install_id="4" * 32,
        recovery_count=count,
    )
    with pytest.raises(ActiveInstallAttemptError, match="maintenance"):
        InstallReceiptGate(executor=executor, http=DynamicStatusHttp(tmp_path)).resume_or_create(
            _archive(tmp_path),
            tmp_path,
            attempt_kind="install",
            overwrite=False,
            before_create=lambda: pytest.fail("must not create"),
            verify_succeeded=lambda _job: None,
        )
    assert all(call[0] != "curl" for call in executor.calls)


def test_intent_and_receipt_never_persist_secure_cookie(tmp_path: Path) -> None:
    secret = "private-cookie-value"
    (tmp_path / "hans.jwt").write_text(secret, encoding="utf-8")
    executor = IntakeExecutor(tmp_path, install_id="5" * 32)
    InstallReceiptGate(
        executor=executor,
        http=DynamicStatusHttp(tmp_path),
    ).resume_or_create(
        _archive(tmp_path),
        tmp_path,
        attempt_kind="install",
        overwrite=False,
        before_create=lambda: None,
        verify_succeeded=lambda _job: None,
    )
    evidence = (tmp_path / "install-intent.json").read_text()
    evidence += (tmp_path / "install-attempt.json").read_text()
    assert secret not in evidence


def test_existing_known_good_evidence_is_verified_and_reused(tmp_path: Path) -> None:
    raw_manifest = b"code: mindscape_cloud_integration\nversion: 1.2.3\n"
    manifest_hash = hashlib.sha256(raw_manifest).hexdigest()
    archive = tmp_path / "known-good-mindscape_cloud_integration-1.2.3.mindpack"
    manifest = tmp_path / "manifest.yaml"
    manifest.write_bytes(raw_manifest)
    with tarfile.open(archive, "w:gz") as handle:
        handle.add(manifest, arcname="mindscape_cloud_integration/manifest.yaml")
    archive.chmod(0o600)
    install_id = "6" * 32
    source_path = f"/app/data/capability-install-jobs/{install_id}/input.mindpack"
    evidence = {
        "schema_version": 1,
        "capability_code": "mindscape_cloud_integration",
        "version": "1.2.3",
        "manifest_hash": manifest_hash,
        "source_kind": "file_upload",
        "source_install_id": install_id,
        "source_container_path": source_path,
        "archive_file": archive.name,
        "archive_sha256": hashlib.sha256(archive.read_bytes()).hexdigest(),
        "captured_at": "2026-07-13T00:00:00+00:00",
    }
    write_private_json(tmp_path / "known-good-pack.json", evidence)

    class SourceExecutor:
        def __init__(self) -> None:
            self.calls = []

        def run(self, args, **_kwargs) -> str:
            self.calls.append(list(args))
            return json.dumps(
                {
                    "install_id": install_id,
                    "source_kind": "file_upload",
                    "source_path": source_path,
                    "version": "1.2.3",
                    "manifest_hash": manifest_hash,
                }
            )

    executor = SourceExecutor()
    gate = PackReleaseGate(
        cloud_worktree=REPO_ROOT,
        executor=executor,
        http=object(),
    )
    assert gate.capture_known_good(tmp_path) == evidence
    assert len(executor.calls) == 1
    assert executor.calls[0][0] == "docker"
