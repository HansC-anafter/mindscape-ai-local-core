from __future__ import annotations

import argparse
import time
from typing import Any

import requests

from .events import emit
from .source_uri import capture_input_kind, public_input_uri
from .settings import (
    DEFAULT_API_RETRY_BACKOFF_SEC,
    DEFAULT_API_RETRY_COUNT,
    DEFAULT_API_TIMEOUT_SEC,
)


def _bounded_response_detail(response: requests.Response) -> str:
    try:
        payload = response.json()
    except ValueError:
        payload = response.text
    if isinstance(payload, dict):
        payload = payload.get("detail") or payload.get("error") or payload.get("message") or payload
    detail = str(payload).replace("\n", " ").strip()
    return detail[:1000] or "no_response_detail"


def api_post(
    api_base: str,
    path: str,
    payload: dict[str, Any],
    *,
    timeout_sec: float = DEFAULT_API_TIMEOUT_SEC,
    retry_count: int = DEFAULT_API_RETRY_COUNT,
    retry_backoff_sec: float = DEFAULT_API_RETRY_BACKOFF_SEC,
) -> dict[str, Any]:
    url = f"{api_base.rstrip('/')}{path}"
    attempts = max(1, retry_count)
    for attempt in range(1, attempts + 1):
        response: requests.Response | None = None
        try:
            response = requests.post(url, json=payload, timeout=timeout_sec)
            response.raise_for_status()
            return response.json()
        except requests.HTTPError as exc:
            status_code = response.status_code if response is not None else None
            if status_code is not None and status_code < 500:
                detail = _bounded_response_detail(response)
                raise RuntimeError(
                    f"api_post_rejected:{status_code}:{path}:{detail}"
                ) from exc
            error: Exception = exc
        except requests.RequestException as exc:
            error = exc
        if attempt >= attempts:
            emit(
                {
                    "event": "api_post_failed",
                    "path": path,
                    "attempt": attempt,
                    "error": str(error),
                }
            )
            raise error
        emit(
            {
                "event": "api_post_retry",
                "path": path,
                "attempt": attempt,
                "next_attempt": attempt + 1,
                "error": str(error),
            }
        )
        time.sleep(max(0.0, retry_backoff_sec) * attempt)
    raise RuntimeError(f"unreachable api retry state for {path}")


def register_live_session(args: argparse.Namespace) -> str:
    metadata: dict[str, Any] = {
        "source_surface": "live_motion_receiver",
        "transport_kind": getattr(args, "transport_kind", "local_rtmp"),
        "capture_input_kind": capture_input_kind(
            getattr(args, "source_kind", ""),
            getattr(args, "transport_kind", ""),
        ),
        "source_kind": getattr(args, "source_kind", "external_stream"),
        "source_session_id": args.source_session_id,
        "media_session_id": getattr(args, "media_session_id", "") or None,
    }
    if str(getattr(args, "append_owner_id", "") or "").strip():
        metadata["append_owner_required"] = True
    if str(args.rtmp_url).startswith(("rtmp://", "rtmps://")):
        metadata["rtmp_origin"] = public_input_uri(args.rtmp_url)
    stream_cost = getattr(args, "stream_cost_metadata", None)
    if isinstance(stream_cost, dict):
        metadata["stream_cost"] = stream_cost
    payload = {
        "live_session_id": args.live_session_id or None,
        "workspace_id": args.workspace_id,
        "capture_session_id": args.source_session_id,
        "device_profile_ref": f"mindscape://device_binding/session/{args.source_session_id}",
        "meeting_session_id": args.meeting_id,
        "metadata": metadata,
    }
    result = api_post(
        args.api_base,
        "/api/v1/capabilities/motion_runtime/analysis/live-sessions",
        payload,
        timeout_sec=args.api_timeout_sec,
        retry_count=args.api_retry_count,
        retry_backoff_sec=args.api_retry_backoff_sec,
    )
    live_session_id = result["live_session"]["live_session_id"]
    emit(
        {
            "event": "live_session_registered",
            "live_session_id": live_session_id,
            "workspace_id": args.workspace_id,
            "meeting_id": args.meeting_id,
        }
    )
    return live_session_id


def append_motion_window(
    *,
    api_base: str,
    summary: dict[str, Any],
    received_at_ms: float,
    api_timeout_sec: float,
    api_retry_count: int,
    api_retry_backoff_sec: float,
    append_owner_id: str = "",
) -> dict[str, Any]:
    return api_post(
        api_base,
        "/api/v1/capabilities/motion_runtime/analysis/motion-windows",
        {
            "motion_window_summary": summary,
            "received_at_ms": received_at_ms,
            "append_owner_id": append_owner_id or None,
        },
        timeout_sec=api_timeout_sec,
        retry_count=api_retry_count,
        retry_backoff_sec=api_retry_backoff_sec,
    )


def emit_rollup(
    args: argparse.Namespace,
    live_session_id: str,
    *,
    motion_reference_profile: dict[str, Any] | None = None,
) -> dict[str, Any]:
    metadata: dict[str, Any] = {"validation_source": "live_motion_receiver"}
    if args.expected_duration_ms:
        metadata["expected_duration_ms"] = args.expected_duration_ms
    if motion_reference_profile is not None:
        metadata["motion_reference_profile"] = motion_reference_profile
    stream_cost = getattr(args, "stream_cost_metadata", None)
    if isinstance(stream_cost, dict):
        metadata["stream_cost"] = stream_cost
    result = api_post(
        args.api_base,
        "/api/v1/capabilities/motion_runtime/analysis/session-rollups",
        {
            "live_session_id": live_session_id,
            "instruction_refs": [],
            "max_window_refs": args.max_window_refs,
            "max_top_findings": 8,
            "metadata": metadata,
        },
        timeout_sec=args.api_timeout_sec,
        retry_count=args.api_retry_count,
        retry_backoff_sec=args.api_retry_backoff_sec,
    )
    summary = result.get("summary") or {}
    rollup_metadata = summary.get("metadata") or {}
    ledger = rollup_metadata.get("reference_segment_ledger") or {}
    artifact_registry = result.get("artifact_registry") or {}
    emit(
        {
            "event": "rollup_probe",
            "live_session_id": live_session_id,
            "window_count": summary.get("window_count"),
            "duration_ms": summary.get("duration_ms"),
            "segmentation_mode": ledger.get("segmentation_mode"),
            "observed_segment_count": ledger.get("observed_segment_count"),
            "observed_checkpoint_count": ledger.get("observed_checkpoint_count"),
            "observed_window_count": ledger.get("observed_window_count"),
            "missing_segment_count": len(ledger.get("missing_segment_indexes") or []),
            "missing_checkpoint_count": len(ledger.get("missing_checkpoint_indexes") or []),
            "validation_requested": ledger.get("validation_requested"),
            "validation_ready": ledger.get("validation_ready"),
            "validation_passed": ledger.get("validation_passed"),
            "missing_validation_checkpoint_count": len(
                ledger.get("missing_validation_checkpoint_indexes") or []
            ),
            "artifact_id": result.get("artifact_id"),
            "artifact_registry_status": artifact_registry.get("status"),
            "artifact_registry_reason": artifact_registry.get("reason"),
        }
    )
    return result
