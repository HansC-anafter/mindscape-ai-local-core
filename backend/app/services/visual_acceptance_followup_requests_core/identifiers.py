"""Identifier helpers for visual acceptance follow-up artifacts."""

import hashlib
import re
import uuid
from datetime import datetime, timezone

from .constants import _MAX_ARTIFACT_ID_LENGTH


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _safe_segment(value: str, fallback: str) -> str:
    candidate = re.sub(r"[^A-Za-z0-9_.-]+", "_", str(value or "").strip())
    return candidate or fallback


def _bounded_identifier(value: str, fallback: str) -> str:
    candidate = _safe_segment(value, fallback)
    if len(candidate) <= _MAX_ARTIFACT_ID_LENGTH:
        return candidate
    digest = hashlib.sha1(candidate.encode("utf-8")).hexdigest()[:12]
    head = candidate[: _MAX_ARTIFACT_ID_LENGTH - len(digest) - 1].rstrip("_")
    return f"{head}_{digest}" if head else digest


def _bounded_execution_id(value: str, fallback: str) -> str:
    return _bounded_identifier(value, fallback)


def _request_artifact_id(review_bundle_id: str, lane_id: str) -> str:
    return _bounded_identifier(
        f"vafreq_{_safe_segment(review_bundle_id, 'bundle')}_{_safe_segment(lane_id, 'lane')}",
        "vafreq_request",
    )


def _dispatch_artifact_id(request_id: str) -> str:
    return _bounded_identifier(
        f"vafdispatch_{_safe_segment(request_id, 'request')}_{uuid.uuid4().hex[:8]}",
        "vafdispatch_request",
    )


def _scene_review_artifact_id(request_id: str) -> str:
    return _bounded_identifier(
        f"vasr_{_safe_segment(request_id, 'request')}",
        "vasr_request",
    )
