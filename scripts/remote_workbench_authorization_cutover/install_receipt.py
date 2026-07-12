"""Exact accepted-install receipt readback before any restore intake."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from .http import HttpClient
from .install_state import ActiveInstallAttemptError
from .io import CutoverError, assert_private_file, write_private_json


_INSTALL_ID = re.compile(r"^[a-f0-9]{32}$")
_TERMINAL_STATES = {"succeeded", "failed"}


def write_install_attempt(
    directory: Path,
    *,
    attempt_kind: str,
    install_id: str,
    state: str,
    terminal: bool,
    attempt_round: int,
) -> None:
    if (
        attempt_kind not in {"install", "restore"}
        or not _INSTALL_ID.fullmatch(install_id)
        or type(attempt_round) is not int
        or attempt_round < 1
    ):
        raise CutoverError("Install attempt receipt identity is invalid")
    write_private_json(
        directory / f"{attempt_kind}-attempt.json",
        {
            "attempt_kind": attempt_kind,
            "attempt_round": attempt_round,
            "install_id": install_id,
            "state": state,
            "terminal": terminal,
        },
    )


def require_terminal_install_attempt(
    http: HttpClient,
    secure_dir: Path,
    *,
    attempt_kind: str = "install",
) -> dict[str, Any]:
    """Refresh the exact accepted job and reject active or indeterminate state."""

    if attempt_kind not in {"install", "restore"}:
        raise CutoverError("Install attempt kind is invalid")
    path = secure_dir / f"{attempt_kind}-attempt.json"
    assert_private_file(path, max_bytes=4_096)
    try:
        receipt = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        raise CutoverError("Install attempt receipt is malformed") from error
    install_id = str(receipt.get("install_id") or "") if isinstance(receipt, dict) else ""
    if (
        not isinstance(receipt, dict)
        or set(receipt) != {
            "attempt_kind", "attempt_round", "install_id", "state", "terminal"
        }
        or receipt.get("attempt_kind") != attempt_kind
        or type(receipt.get("attempt_round")) is not int
        or receipt.get("attempt_round") < 1
        or not _INSTALL_ID.fullmatch(install_id)
    ):
        raise CutoverError("Install attempt receipt identity is invalid")
    try:
        job = http.get_json(
            f"http://localhost:8220/api/v1/capability-packs/install-jobs/{install_id}",
            timeout_seconds=10.0,
            max_response_bytes=262_144,
        )
    except Exception as error:  # noqa: BLE001 - status is now indeterminate
        raise ActiveInstallAttemptError(
            "Accepted install status is indeterminate; restore is blocked"
        ) from error
    state = str(job.get("state") or "")
    if state not in _TERMINAL_STATES:
        raise ActiveInstallAttemptError(
            "Accepted install is active or indeterminate; restore is blocked"
        )
    write_install_attempt(
        secure_dir,
        attempt_kind=attempt_kind,
        install_id=install_id,
        state=state,
        terminal=True,
        attempt_round=receipt["attempt_round"],
    )
    return job


def next_restore_attempt_round(secure_dir: Path) -> int:
    """Allow a new restore only after an exact terminal failed prior round."""

    path = secure_dir / "restore-attempt.json"
    if not path.exists():
        return 1
    assert_private_file(path, max_bytes=4_096)
    try:
        receipt = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        raise CutoverError("Restore attempt receipt is malformed") from error
    if (
        not isinstance(receipt, dict)
        or set(receipt) != {
            "attempt_kind", "attempt_round", "install_id", "state", "terminal"
        }
        or receipt.get("attempt_kind") != "restore"
        or not _INSTALL_ID.fullmatch(str(receipt.get("install_id") or ""))
        or receipt.get("state") != "failed"
        or receipt.get("terminal") is not True
        or type(receipt.get("attempt_round")) is not int
        or receipt["attempt_round"] < 1
    ):
        raise CutoverError("A new restore round is not permitted by the fixed receipt")
    return receipt["attempt_round"] + 1


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
