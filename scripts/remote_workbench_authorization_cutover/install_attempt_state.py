"""Strict private intent and receipt state for durable pack installs."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from .http import HttpClient
from .install_state import ActiveInstallAttemptError
from .io import CutoverError, assert_private_file, write_private_json


ACTIVE_INSTALL_STATES = (
    "queued",
    "running",
    "waiting_db",
    "pending_execution_activation",
)
INSTALL_POLL_BUDGET_SECONDS = 600.0
MAX_PACK_BYTES = 128 * 1024 * 1024

_INSTALL_ID = re.compile(r"^[a-f0-9]{32}$")
_ARCHIVE_HASH = re.compile(r"^[a-f0-9]{64}$")
_MULTIPART_FILENAME = re.compile(
    r"^remote-workbench-(install|restore)-([a-f0-9]{32})\.mindpack$"
)
_ARTIFACT_PATH = re.compile(
    r"^/app/data/capability-install-jobs/([a-f0-9]{32})/input\.mindpack$"
)
_INTENT_KEYS = {
    "schema_version",
    "attempt_kind",
    "attempt_round",
    "archive_sha256",
    "multipart_filename",
}
_RECEIPT_KEYS = _INTENT_KEYS | {"install_id", "state", "terminal"}


def _attempt_path(directory: Path, attempt_kind: str, suffix: str) -> Path:
    if attempt_kind not in {"install", "restore"}:
        raise CutoverError("Install attempt kind is invalid")
    return directory / f"{attempt_kind}-{suffix}.json"


def _read_optional_private_json(path: Path) -> dict[str, Any] | None:
    if path.is_symlink():
        raise CutoverError(f"Symbolic links are not allowed: {path.name}")
    if not path.exists():
        return None
    assert_private_file(path, max_bytes=4_096)
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        raise CutoverError(f"{path.name} is malformed") from error
    if not isinstance(payload, dict):
        raise CutoverError(f"{path.name} must be an object")
    return payload


def _validate_context(
    payload: dict[str, Any],
    *,
    attempt_kind: str,
    receipt: bool,
) -> dict[str, Any]:
    expected_keys = _RECEIPT_KEYS if receipt else _INTENT_KEYS
    filename = str(payload.get("multipart_filename") or "")
    filename_match = _MULTIPART_FILENAME.fullmatch(filename)
    if (
        set(payload) != expected_keys
        or payload.get("schema_version") != 1
        or payload.get("attempt_kind") != attempt_kind
        or type(payload.get("attempt_round")) is not int
        or payload["attempt_round"] < 1
        or not _ARCHIVE_HASH.fullmatch(str(payload.get("archive_sha256") or ""))
        or filename_match is None
        or filename_match.group(1) != attempt_kind
    ):
        raise CutoverError("Install intent or receipt identity is invalid")
    if receipt:
        state = str(payload.get("state") or "")
        terminal = payload.get("terminal")
        if (
            not _INSTALL_ID.fullmatch(str(payload.get("install_id") or ""))
            or type(terminal) is not bool
            or not state
            or len(state) > 64
            or (terminal is True) != (state in {"succeeded", "failed"})
        ):
            raise CutoverError("Install attempt receipt state is invalid")
    return payload


def load_install_intent(
    directory: Path,
    *,
    attempt_kind: str,
) -> dict[str, Any] | None:
    payload = _read_optional_private_json(
        _attempt_path(directory, attempt_kind, "intent")
    )
    return (
        _validate_context(payload, attempt_kind=attempt_kind, receipt=False)
        if payload is not None
        else None
    )


def load_install_attempt(
    directory: Path,
    *,
    attempt_kind: str,
) -> dict[str, Any] | None:
    payload = _read_optional_private_json(
        _attempt_path(directory, attempt_kind, "attempt")
    )
    return (
        _validate_context(payload, attempt_kind=attempt_kind, receipt=True)
        if payload is not None
        else None
    )


def write_install_intent(
    directory: Path,
    *,
    attempt_kind: str,
    attempt_round: int,
    archive_sha256: str,
    multipart_filename: str,
) -> dict[str, Any]:
    payload = _validate_context(
        {
            "schema_version": 1,
            "attempt_kind": attempt_kind,
            "attempt_round": attempt_round,
            "archive_sha256": archive_sha256,
            "multipart_filename": multipart_filename,
        },
        attempt_kind=attempt_kind,
        receipt=False,
    )
    write_private_json(
        _attempt_path(directory, attempt_kind, "intent"),
        payload,
    )
    return payload


def write_install_attempt(
    directory: Path,
    *,
    intent: dict[str, Any],
    install_id: str,
    state: str,
    terminal: bool,
) -> None:
    attempt_kind = str(intent.get("attempt_kind") or "")
    context = _validate_context(
        dict(intent),
        attempt_kind=attempt_kind,
        receipt=False,
    )
    payload = {
        **context,
        "install_id": install_id,
        "state": state,
        "terminal": terminal,
    }
    _validate_context(payload, attempt_kind=attempt_kind, receipt=True)
    write_private_json(
        _attempt_path(directory, attempt_kind, "attempt"),
        payload,
    )


def contexts_match(
    intent: dict[str, Any],
    receipt: dict[str, Any],
) -> bool:
    return all(intent[key] == receipt[key] for key in _INTENT_KEYS)


def validate_job_identity(
    job: dict[str, Any],
    *,
    intent: dict[str, Any],
    expected_install_id: str,
) -> str:
    source_payload = job.get("source_payload")
    source_path = (
        str(source_payload.get("mindpack_path") or "")
        if isinstance(source_payload, dict)
        else ""
    )
    path_match = _ARTIFACT_PATH.fullmatch(source_path)
    state = str(job.get("state") or "")
    if (
        job.get("install_id") != expected_install_id
        or job.get("source_kind") != "file_upload"
        or not isinstance(source_payload, dict)
        or source_payload.get("filename") != intent["multipart_filename"]
        or path_match is None
        or path_match.group(1) != expected_install_id
        or state not in {*ACTIVE_INSTALL_STATES, "succeeded", "failed"}
    ):
        raise ActiveInstallAttemptError(
            "Accepted install identity or state is indeterminate; maintenance is required"
        )
    return state


def refresh_exact_attempt(
    http: HttpClient,
    secure_dir: Path,
    *,
    intent: dict[str, Any],
    receipt: dict[str, Any],
) -> dict[str, Any]:
    install_id = str(receipt["install_id"])
    try:
        job = http.get_json(
            f"http://localhost:8220/api/v1/capability-packs/install-jobs/{install_id}",
            timeout_seconds=10.0,
            max_response_bytes=262_144,
        )
    except Exception as error:  # noqa: BLE001 - exact status is indeterminate
        raise ActiveInstallAttemptError(
            "Accepted install status is indeterminate; maintenance is required"
        ) from error
    if not isinstance(job, dict):
        raise ActiveInstallAttemptError(
            "Accepted install status is indeterminate; maintenance is required"
        )
    state = validate_job_identity(
        job,
        intent=intent,
        expected_install_id=install_id,
    )
    if receipt["terminal"] is True and receipt["state"] != state:
        raise ActiveInstallAttemptError(
            "Accepted install terminal state changed; maintenance is required"
        )
    write_install_attempt(
        secure_dir,
        intent=intent,
        install_id=install_id,
        state=state,
        terminal=state in {"succeeded", "failed"},
    )
    return job


def require_terminal_install_attempt(
    http: HttpClient,
    secure_dir: Path,
    *,
    attempt_kind: str = "install",
) -> dict[str, Any]:
    """Refresh one exact accepted job and reject active or indeterminate state."""

    intent = load_install_intent(secure_dir, attempt_kind=attempt_kind)
    receipt = load_install_attempt(secure_dir, attempt_kind=attempt_kind)
    if intent is None or receipt is None or not contexts_match(intent, receipt):
        raise CutoverError("Install intent and attempt receipt do not identify one round")
    job = refresh_exact_attempt(
        http,
        secure_dir,
        intent=intent,
        receipt=receipt,
    )
    if job.get("state") not in {"succeeded", "failed"}:
        raise ActiveInstallAttemptError(
            "Accepted install is active; maintenance is required"
        )
    return job


def next_restore_attempt_round(secure_dir: Path) -> int:
    """Return the next restore round only after one exact failed receipt."""

    intent = load_install_intent(secure_dir, attempt_kind="restore")
    receipt = load_install_attempt(secure_dir, attempt_kind="restore")
    if (
        intent is None
        or receipt is None
        or not contexts_match(intent, receipt)
        or receipt["state"] != "failed"
        or receipt["terminal"] is not True
    ):
        raise CutoverError("A new restore round is not permitted by the fixed receipt")
    return int(receipt["attempt_round"]) + 1


def verify_known_good_restore_job(secure_dir: Path, job: dict[str, Any]) -> None:
    """Match a terminal restore job to the fixed known-good identity evidence."""

    path = secure_dir / "known-good-pack.json"
    assert_private_file(path, max_bytes=32_768)
    try:
        evidence = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        raise CutoverError("Known-good pack evidence is malformed") from error
    result = job.get("result_payload") if isinstance(job, dict) else None
    activation = result.get("activation") if isinstance(result, dict) else None
    if (
        not isinstance(evidence, dict)
        or evidence.get("schema_version") != 1
        or not isinstance(activation, dict)
        or result.get("version") != evidence.get("version")
        or activation.get("manifest_hash") != evidence.get("manifest_hash")
    ):
        raise CutoverError("Terminal restore job does not match known-good evidence")
