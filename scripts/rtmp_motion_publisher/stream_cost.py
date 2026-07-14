from __future__ import annotations

import argparse
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable
from urllib.parse import urlsplit

from .events import emit


StreamCostTool = Callable[..., dict[str, Any]]


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _ensure_backend_app_path() -> None:
    backend_app = _repo_root() / "backend" / "app"
    if str(backend_app) not in sys.path:
        sys.path.insert(0, str(backend_app))


def _load_stream_cost_tool() -> StreamCostTool:
    _ensure_backend_app_path()
    from capabilities.camera_capture_control.tools.scc_estimate_stream_cost import (
        scc_estimate_stream_cost,
    )

    return scc_estimate_stream_cost


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _frame_dimensions(frame: Any) -> tuple[int, int]:
    shape = getattr(frame, "shape", None)
    if not shape or len(shape) < 2:
        return 0, 0
    return int(shape[1]), int(shape[0])


def _quality_snapshot(
    args: argparse.Namespace,
    frame: Any,
    *,
    observed_at: str,
) -> dict[str, Any]:
    configured_width = int(getattr(args, "stream_cost_source_width", 0) or 0)
    configured_height = int(getattr(args, "stream_cost_source_height", 0) or 0)
    if configured_width > 0 and configured_height > 0:
        width, height = configured_width, configured_height
        basis = "configured_transport_quality"
    else:
        width, height = _frame_dimensions(frame)
        basis = (
            "analysis_output"
            if getattr(args, "capture_backend", "") == "ffmpeg"
            else "decoded_frame"
        )
    configured_tier = getattr(args, "stream_cost_billing_tier", None)
    quality: dict[str, Any] = {
        "observed_at": observed_at,
        "width_px": width,
        "height_px": height,
        "frame_rate": float(
            getattr(args, "stream_cost_source_fps", 0.0)
            or getattr(args, "sample_fps", 0.0)
            or 0.0
        ),
        "bitrate_mbps": float(
            getattr(args, "stream_cost_source_bitrate_mbps", 0.0) or 0.0
        ),
        "codec": str(getattr(args, "stream_cost_codec", "h264") or "h264"),
        "basis": basis,
    }
    if configured_tier:
        quality["tier"] = configured_tier
    return quality


def _stream_transport(args: argparse.Namespace) -> str:
    configured = str(getattr(args, "stream_cost_transport", "") or "").strip()
    if configured:
        return configured
    source = str(getattr(args, "rtmp_url", "") or "")
    return urlsplit(source).scheme or "stream"


class StreamCostTracker:
    """Bridge the host pull lifecycle to camera_capture_control's cost tool."""

    def __init__(
        self,
        *,
        args: argparse.Namespace,
        tool: StreamCostTool,
        metadata: dict[str, Any],
        started_at_monotonic: float,
    ) -> None:
        self.args = args
        self.tool = tool
        self.metadata = metadata
        self.started_at_monotonic = started_at_monotonic
        self.finished = False

    @classmethod
    def start(
        cls,
        args: argparse.Namespace,
        first_frame: Any,
    ) -> StreamCostTracker | None:
        if bool(getattr(args, "disable_stream_cost", False)):
            return None
        started_at = _utc_now_iso()
        started_at_monotonic = time.monotonic()
        try:
            tool = _load_stream_cost_tool()
            expected_duration_sec = max(
                float(getattr(args, "duration_sec", 0.0) or 0.0),
                float(getattr(args, "expected_duration_ms", 0.0) or 0.0) / 1000.0,
            )
            response = tool(
                action="start",
                provider=str(getattr(args, "stream_cost_provider", "local") or "local"),
                region=str(getattr(args, "stream_cost_region", "") or ""),
                direction=str(
                    getattr(args, "stream_cost_direction", "remote_pull")
                    or "remote_pull"
                ),
                transport=_stream_transport(args),
                codec=str(getattr(args, "stream_cost_codec", "h264") or "h264"),
                quality_start=_quality_snapshot(
                    args,
                    first_frame,
                    observed_at=started_at,
                ),
                configured_billing_tier=getattr(
                    args,
                    "stream_cost_billing_tier",
                    None,
                ),
                expected_duration_sec=expected_duration_sec,
                observed_at=started_at,
            )
            metadata = response["stream_cost"]
            if not isinstance(metadata, dict):
                raise TypeError("stream_cost_tool_returned_invalid_metadata")
            args.stream_cost_metadata = metadata
            emit(
                {
                    "event": "stream_cost_quoted",
                    "provider": metadata.get("provider"),
                    "region": metadata.get("region"),
                    "quality_tier": (metadata.get("rate_snapshot") or {}).get(
                        "quality_tier"
                    ),
                    "quote_id": (metadata.get("rate_snapshot") or {}).get("quote_id"),
                    "stream_cost": metadata,
                }
            )
            return cls(
                args=args,
                tool=tool,
                metadata=metadata,
                started_at_monotonic=started_at_monotonic,
            )
        except Exception as exc:
            emit(
                {
                    "event": "stream_cost_unavailable",
                    "phase": "start",
                    "provider": str(
                        getattr(args, "stream_cost_provider", "local") or "local"
                    ),
                    "error": str(exc),
                }
            )
            return None

    def finish(self, last_frame: Any) -> dict[str, Any]:
        if self.finished:
            return self.metadata
        ended_at = _utc_now_iso()
        duration_sec = max(0.0, time.monotonic() - self.started_at_monotonic)
        try:
            response = self.tool(
                action="finish",
                stream_cost=self.metadata,
                quality_end=_quality_snapshot(
                    self.args,
                    last_frame,
                    observed_at=ended_at,
                ),
                duration_sec=duration_sec,
                observed_at=ended_at,
            )
            metadata = response["stream_cost"]
            if not isinstance(metadata, dict):
                raise TypeError("stream_cost_tool_returned_invalid_metadata")
            self.metadata = metadata
            self.args.stream_cost_metadata = metadata
            self.finished = True
            estimate = metadata.get("estimate") or {}
            emit(
                {
                    "event": "stream_cost_estimated",
                    "provider": metadata.get("provider"),
                    "region": metadata.get("region"),
                    "quality_tier": estimate.get("billing_tier"),
                    "currency": estimate.get("currency"),
                    "amount": estimate.get("amount"),
                    "duration_sec": estimate.get("observed_duration_sec"),
                    "quote_id": (metadata.get("rate_snapshot") or {}).get("quote_id"),
                    "stream_cost": metadata,
                }
            )
            return metadata
        except Exception as exc:
            emit(
                {
                    "event": "stream_cost_unavailable",
                    "phase": "finish",
                    "provider": self.metadata.get("provider"),
                    "quote_id": (self.metadata.get("rate_snapshot") or {}).get(
                        "quote_id"
                    ),
                    "error": str(exc),
                }
            )
            return self.metadata


def start_stream_cost_tracking(
    args: argparse.Namespace,
    first_frame: Any,
) -> StreamCostTracker | None:
    return StreamCostTracker.start(args, first_frame)


__all__ = ["StreamCostTracker", "start_stream_cost_tracking"]
