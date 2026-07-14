from __future__ import annotations

import argparse
import json
import os
import stat
import time
from pathlib import Path
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from .app import run_receiver
from .cli import parse_args
from .receiver_state import safe_receiver_failure_reason, transition_receiver_state


def _required(record: dict[str, Any], name: str) -> str:
    value = str(record.get(name) or "").strip()
    if not value:
        raise ValueError(f"receiver_descriptor_missing_{name}")
    return value


def _load_descriptor(path: Path) -> dict[str, Any]:
    mode = stat.S_IMODE(path.stat().st_mode)
    if mode & 0o077:
        raise ValueError("receiver_descriptor_permissions_invalid")
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("receiver_descriptor_invalid")
    if payload.get("schema_version") != "live_media_receiver.v1":
        raise ValueError("receiver_descriptor_schema_invalid")
    if _required(payload, "transport_kind") != "rtsps":
        raise ValueError("receiver_transport_not_supported")
    if not _required(payload, "input_url").startswith("rtsps://"):
        raise ValueError("receiver_input_must_use_rtsps")
    if float(payload.get("expires_at_epoch") or 0) <= time.time():
        raise ValueError("receiver_descriptor_expired")
    for name in (
        "workspace_id",
        "device_session_id",
        "media_session_id",
        "live_motion_session_id",
        "meeting_session_id",
        "practice_session_id",
        "receiver_identity",
        "append_owner_id",
        "access_token",
        "api_base",
        "coach_pack",
        "practice_mode",
    ):
        _required(payload, name)
    return payload


def _authenticated_input_url(input_url: str, access_token: str) -> str:
    parsed = urlsplit(input_url)
    query = dict(parse_qsl(parsed.query, keep_blank_values=True))
    query["token"] = access_token
    return urlunsplit((parsed.scheme, parsed.netloc, parsed.path, urlencode(query), ""))


def _evidence_paths(descriptor: dict[str, Any]) -> tuple[str, str]:
    data_root = Path(
        os.environ.get("LOCAL_CORE_DATA_HOST_DIR")
        or Path(__file__).resolve().parents[2] / "data"
    )
    relative = (
        Path("workspaces")
        / _required(descriptor, "workspace_id")
        / "artifacts/yogacoach/live-capture"
        / _required(descriptor, "live_motion_session_id")
    )
    host_path = data_root / relative
    storage_path = Path("/app/data") / relative
    host_path.mkdir(parents=True, exist_ok=True)
    return str(host_path), str(storage_path)


def _motion_reference_profile_path(descriptor: dict[str, Any]) -> str:
    profile = descriptor.get("motion_reference_profile")
    if profile is None:
        return ""
    if not isinstance(profile, dict):
        raise ValueError("motion_reference_profile_ref_invalid")
    for name in ("artifact_id", "storage_ref", "reference_profile_id"):
        _required(profile, name)
    raw_path = _required(descriptor, "motion_reference_profile_path")
    profile_path = Path(raw_path).resolve(strict=True)
    data_root = Path(
        os.environ.get("LOCAL_CORE_DATA_HOST_DIR")
        or Path(__file__).resolve().parents[2] / "data"
    ).resolve()
    allowed_root = (
        data_root
        / "workspaces"
        / _required(descriptor, "workspace_id")
        / "artifacts/yogacoach/reference-profiles"
    ).resolve()
    try:
        profile_path.relative_to(allowed_root)
    except ValueError as exc:
        raise ValueError("motion_reference_profile_path_outside_workspace") from exc
    if not profile_path.is_file():
        raise ValueError("motion_reference_profile_file_not_found")
    return str(profile_path)


def _build_receiver_args(
    descriptor: dict[str, Any],
    *,
    state_path: Path,
) -> argparse.Namespace:
    remaining_sec = max(1.0, float(descriptor["expires_at_epoch"]) - time.time())
    expected_duration_ms = max(0.0, float(descriptor.get("expected_duration_ms") or 0))
    duration_sec = min(
        remaining_sec,
        expected_duration_ms / 1000.0 if expected_duration_ms else remaining_sec,
    )
    evidence_output, evidence_storage = _evidence_paths(descriptor)
    motion_reference_profile_path = _motion_reference_profile_path(descriptor)
    arguments = [
        "--input-url",
        _authenticated_input_url(
            _required(descriptor, "input_url"),
            _required(descriptor, "access_token"),
        ),
        "--transport-kind",
        "rtsps",
        "--source-kind",
        _required(descriptor, "source_kind"),
        "--api-base",
        _required(descriptor, "api_base"),
        "--workspace-id",
        _required(descriptor, "workspace_id"),
        "--meeting-id",
        _required(descriptor, "meeting_session_id"),
        "--source-session-id",
        _required(descriptor, "device_session_id"),
        "--live-session-id",
        _required(descriptor, "live_motion_session_id"),
        "--practice-session-id",
        _required(descriptor, "practice_session_id"),
        "--media-session-id",
        _required(descriptor, "media_session_id"),
        "--receiver-identity",
        _required(descriptor, "receiver_identity"),
        "--append-owner-id",
        _required(descriptor, "append_owner_id"),
        "--receiver-state-path",
        str(state_path),
        "--duration-sec",
        str(duration_sec),
        "--expected-duration-ms",
        str(expected_duration_ms),
        "--capture-backend",
        "ffmpeg",
        "--api-timeout-sec",
        "5",
        "--rollup-api-timeout-sec",
        "30",
        "--closeout-api-timeout-sec",
        "30",
        "--api-retry-count",
        "2",
        "--api-retry-backoff-sec",
        "0.5",
        "--append-queue-max-size",
        "32",
        "--learner-evidence-output-dir",
        evidence_output,
        "--learner-evidence-storage-dir",
        evidence_storage,
        "--stream-reconnect-max-attempts",
        "0",
    ]
    reference_url = str(descriptor.get("reference_url") or "").strip()
    if reference_url:
        arguments.extend(["--yogacoach-reference-url", reference_url])
    if motion_reference_profile_path:
        arguments.extend(
            ["--motion-reference-profile-path", motion_reference_profile_path]
        )
        profile_ref = descriptor.get("motion_reference_profile") or {}
        arguments.extend(
            [
                "--motion-reference-profile-artifact-id",
                _required(profile_ref, "artifact_id"),
            ]
        )
    user_goal = str(descriptor.get("user_goal") or "").strip()
    if user_goal:
        arguments.extend(["--user-goal", user_goal])
    if descriptor.get("coach_pack") == "yogacoach":
        arguments.extend(["--emit-yogacoach-summary", "--materialize-practice-diary"])
    return parse_args(arguments)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--descriptor-path", type=Path, required=True)
    parser.add_argument("--state-path", type=Path, required=True)
    input_args = parser.parse_args()
    try:
        descriptor = _load_descriptor(input_args.descriptor_path)
        receiver_args = _build_receiver_args(
            descriptor,
            state_path=input_args.state_path,
        )
        transition_receiver_state(receiver_args, "waiting_source")
        result = run_receiver(receiver_args)
        terminal_state = "completed" if result == 0 else "failed"
        transition_receiver_state(receiver_args, terminal_state)
        return result
    except Exception as exc:
        fallback = argparse.Namespace(
            receiver_state_path=str(input_args.state_path),
            workspace_id=(locals().get("descriptor") or {}).get("workspace_id", "unknown"),
            media_session_id=(locals().get("descriptor") or {}).get("media_session_id", "unknown"),
            receiver_identity=(locals().get("descriptor") or {}).get("receiver_identity", "unknown"),
        )
        transition_receiver_state(
            fallback,
            "failed",
            reason=safe_receiver_failure_reason(exc),
        )
        return 1


__all__ = ["main"]
