"""Receipt-bound durable install intake and exact response-loss recovery."""

from __future__ import annotations

import hashlib
import json
import time
import uuid
from pathlib import Path
from typing import Any, Callable

from .http import HttpClient
from .install_attempt_state import (
    ACTIVE_INSTALL_STATES,
    INSTALL_POLL_BUDGET_SECONDS,
    MAX_PACK_BYTES,
    _INSTALL_ID as INSTALL_ID_PATTERN,
    contexts_match,
    load_install_attempt,
    load_install_intent,
    next_restore_attempt_round,
    refresh_exact_attempt,
    require_terminal_install_attempt,
    validate_job_identity,
    verify_known_good_restore_job,
    write_install_attempt,
    write_install_intent,
)
from .install_state import AcceptedInstallError, ActiveInstallAttemptError
from .io import CommandExecutor, CutoverError


class InstallReceiptGate:
    """Consume or create exactly one receipt-bound durable install round."""

    def __init__(
        self,
        *,
        executor: CommandExecutor,
        http: HttpClient,
        sleep: Callable[[float], None] = time.sleep,
        monotonic: Callable[[], float] = time.monotonic,
    ) -> None:
        self.executor = executor
        self.http = http
        self.sleep = sleep
        self.monotonic = monotonic

    @staticmethod
    def _sha256(path: Path) -> str:
        if path.is_symlink() or not path.is_file():
            raise CutoverError("Install archive is not a regular file")
        size = path.stat().st_size
        if size <= 0 or size > MAX_PACK_BYTES:
            raise CutoverError("Install archive exceeds its byte budget")
        digest = hashlib.sha256()
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()

    def _recover_by_intent(
        self,
        secure_dir: Path,
        *,
        intent: dict[str, Any],
    ) -> dict[str, Any]:
        sql = """
SELECT COALESCE(json_agg(json_build_object(
  'install_id', install_id,
  'source_kind', source_kind,
  'state', state,
  'source_payload', json_build_object(
    'filename', source_payload->>'filename',
    'mindpack_path', source_payload->>'mindpack_path'
  )
) ORDER BY created_at), '[]'::json)::text
FROM capability_install_jobs
WHERE source_kind = 'file_upload'
  AND source_payload->>'filename' = :'multipart_filename';
""".strip()
        raw = self.executor.run(
            [
                "docker",
                "exec",
                "mindscape-ai-local-core-postgres",
                "psql",
                "-XqAt",
                "-v",
                "ON_ERROR_STOP=1",
                "-v",
                f"multipart_filename={intent['multipart_filename']}",
                "-U",
                "mindscape",
                "-d",
                "mindscape_core",
                "-c",
                sql,
            ],
            timeout_seconds=20.0,
        ).strip()
        try:
            matches = json.loads(raw)
        except json.JSONDecodeError as error:
            raise ActiveInstallAttemptError(
                "Install intent recovery is indeterminate; maintenance is required"
            ) from error
        if not isinstance(matches, list) or len(matches) != 1:
            raise ActiveInstallAttemptError(
                "Install intent recovery did not find one exact job; maintenance is required"
            )
        candidate = matches[0]
        if not isinstance(candidate, dict):
            raise ActiveInstallAttemptError(
                "Install intent recovery is indeterminate; maintenance is required"
            )
        install_id = str(candidate.get("install_id") or "")
        state = validate_job_identity(
            candidate,
            intent=intent,
            expected_install_id=install_id,
        )
        write_install_attempt(
            secure_dir,
            intent=intent,
            install_id=install_id,
            state=state,
            terminal=state in {"succeeded", "failed"},
        )
        return candidate

    def _verify_succeeded(
        self,
        job: dict[str, Any],
        *,
        verify_succeeded: Callable[[dict[str, Any]], None],
    ) -> None:
        result = job.get("result_payload")
        activation = (
            result.get("execution_activation") if isinstance(result, dict) else None
        )
        if not isinstance(activation, dict) or activation.get("state") in {
            None,
            "pending",
            "pending_execution_activation",
        }:
            raise AcceptedInstallError(
                "Execution activation remains pending",
                install_id=str(job.get("install_id") or ""),
                state="succeeded",
                terminal=True,
            )
        try:
            verify_succeeded(job)
        except Exception as error:  # noqa: BLE001 - retain terminal receipt
            raise AcceptedInstallError(
                "Installed runtime verification failed",
                install_id=str(job.get("install_id") or ""),
                state="succeeded",
                terminal=True,
            ) from error

    def _poll(
        self,
        secure_dir: Path,
        *,
        intent: dict[str, Any],
        receipt: dict[str, Any],
        verify_succeeded: Callable[[dict[str, Any]], None],
    ) -> dict[str, Any]:
        install_id = str(receipt["install_id"])
        state = str(receipt["state"])
        deadline = self.monotonic() + INSTALL_POLL_BUDGET_SECONDS
        try:
            while self.monotonic() < deadline:
                job = self.http.get_json(
                    "http://localhost:8220/api/v1/capability-packs/"
                    f"install-jobs/{install_id}",
                    timeout_seconds=10.0,
                    max_response_bytes=262_144,
                )
                if not isinstance(job, dict):
                    raise CutoverError("Install status payload is not an object")
                state = validate_job_identity(
                    job,
                    intent=intent,
                    expected_install_id=install_id,
                )
                terminal = state in {"succeeded", "failed"}
                write_install_attempt(
                    secure_dir,
                    intent=intent,
                    install_id=install_id,
                    state=state,
                    terminal=terminal,
                )
                if state == "succeeded":
                    self._verify_succeeded(job, verify_succeeded=verify_succeeded)
                    return job
                if state == "failed":
                    raise AcceptedInstallError(
                        "Capability install job failed",
                        install_id=install_id,
                        state=state,
                        terminal=True,
                    )
                self.sleep(min(2.0, max(0.0, deadline - self.monotonic())))
        except AcceptedInstallError:
            raise
        except Exception as error:  # noqa: BLE001 - accepted state is indeterminate
            raise AcceptedInstallError(
                "Accepted capability install state became indeterminate",
                install_id=install_id,
                state=state,
                terminal=False,
            ) from error
        raise AcceptedInstallError(
            "Capability install job exceeded its 600 second poll budget",
            install_id=install_id,
            state=state,
            terminal=False,
        )

    def _consume_recovered(
        self,
        secure_dir: Path,
        *,
        intent: dict[str, Any],
        candidate: dict[str, Any],
        verify_succeeded: Callable[[dict[str, Any]], None],
    ) -> dict[str, Any]:
        receipt = load_install_attempt(
            secure_dir,
            attempt_kind=str(intent["attempt_kind"]),
        )
        if receipt is None:
            raise CutoverError("Recovered install receipt was not persisted")
        state = str(candidate.get("state") or "")
        if state == "failed":
            raise AcceptedInstallError(
                "Recovered capability install job failed",
                install_id=str(candidate.get("install_id") or ""),
                state=state,
                terminal=True,
            )
        if state == "succeeded":
            job = refresh_exact_attempt(
                self.http,
                secure_dir,
                intent=intent,
                receipt=receipt,
            )
            self._verify_succeeded(job, verify_succeeded=verify_succeeded)
            return job
        return self._poll(
            secure_dir,
            intent=intent,
            receipt=receipt,
            verify_succeeded=verify_succeeded,
        )

    def resume_or_create(
        self,
        archive: Path,
        secure_dir: Path,
        *,
        attempt_kind: str,
        overwrite: bool,
        before_create: Callable[[], None],
        verify_succeeded: Callable[[dict[str, Any]], None],
    ) -> dict[str, Any]:
        """Resume one exact round or create one new receipt-bound job."""

        intent = load_install_intent(secure_dir, attempt_kind=attempt_kind)
        receipt = load_install_attempt(secure_dir, attempt_kind=attempt_kind)
        next_round = 1
        if receipt is not None and intent is None:
            raise CutoverError("Install receipt exists without its atomic intent")
        if intent is not None:
            if receipt is None:
                recovered = self._recover_by_intent(secure_dir, intent=intent)
                return self._consume_recovered(
                    secure_dir,
                    intent=intent,
                    candidate=recovered,
                    verify_succeeded=verify_succeeded,
                )
            if contexts_match(intent, receipt):
                job = refresh_exact_attempt(
                    self.http,
                    secure_dir,
                    intent=intent,
                    receipt=receipt,
                )
                state = str(job.get("state") or "")
                if state == "succeeded":
                    self._verify_succeeded(job, verify_succeeded=verify_succeeded)
                    return job
                if state in ACTIVE_INSTALL_STATES:
                    raise ActiveInstallAttemptError(
                        "Accepted install remains active; maintenance is required"
                    )
                next_round = int(receipt["attempt_round"]) + 1
            elif (
                receipt["state"] == "failed"
                and receipt["terminal"] is True
                and int(intent["attempt_round"]) == int(receipt["attempt_round"]) + 1
            ):
                recovered = self._recover_by_intent(secure_dir, intent=intent)
                return self._consume_recovered(
                    secure_dir,
                    intent=intent,
                    candidate=recovered,
                    verify_succeeded=verify_succeeded,
                )
            else:
                raise CutoverError("Install intent and receipt rounds are inconsistent")

        before_create()
        archive_sha256 = self._sha256(archive)
        multipart_filename = (
            f"remote-workbench-{attempt_kind}-{uuid.uuid4().hex}.mindpack"
        )
        intent = write_install_intent(
            secure_dir,
            attempt_kind=attempt_kind,
            attempt_round=next_round,
            archive_sha256=archive_sha256,
            multipart_filename=multipart_filename,
        )
        command = [
            "curl",
            "-sS",
            "--fail-with-body",
            "-X",
            "POST",
            "http://localhost:8220/api/v1/capability-packs/install-from-file",
            "-F",
            f"file=@{archive};filename={multipart_filename}",
        ]
        if overwrite:
            command.extend(
                [
                    "-F",
                    "allow_overwrite=true",
                    "-F",
                    "overwrite_confirmation=OVERWRITE",
                    "-F",
                    "overwrite_review_confirmation=REVIEWED_LOCAL_DIFFS",
                ]
            )
        try:
            raw = self.executor.run(command, timeout_seconds=120.0)
            accepted = json.loads(raw)
            install_id = str(accepted.get("install_id") or "")
            state = str(accepted.get("state") or "")
            if (
                not isinstance(accepted, dict)
                or accepted.get("success") is not True
                or accepted.get("accepted") is not True
                or not INSTALL_ID_PATTERN.fullmatch(install_id)
                or accepted.get("status_url")
                != f"/api/v1/capability-packs/install-jobs/{install_id}"
                or state not in ACTIVE_INSTALL_STATES
            ):
                raise CutoverError("Install intake returned an invalid durable job")
        except Exception as intake_error:  # noqa: BLE001 - recover exact DB correlation
            try:
                recovered = self._recover_by_intent(secure_dir, intent=intent)
                return self._consume_recovered(
                    secure_dir,
                    intent=intent,
                    candidate=recovered,
                    verify_succeeded=verify_succeeded,
                )
            except Exception as recovery_error:
                raise recovery_error from intake_error
        write_install_attempt(
            secure_dir,
            intent=intent,
            install_id=install_id,
            state=state,
            terminal=False,
        )
        receipt = load_install_attempt(secure_dir, attempt_kind=attempt_kind)
        if receipt is None:
            raise CutoverError("Accepted install receipt was not persisted")
        return self._poll(
            secure_dir,
            intent=intent,
            receipt=receipt,
            verify_succeeded=verify_succeeded,
        )
