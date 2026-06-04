"""Proxy bounded Whisper transcription requests to the local sidecar."""

from __future__ import annotations

import base64
import os
from dataclasses import dataclass
from typing import Any, Literal

import httpx
from pydantic import BaseModel, Field


DEFAULT_WHISPER_BASE_URL = "http://whisper-service:8006"
MAX_STT_AUDIO_BYTES = 8 * 1024 * 1024
MAX_STT_AUDIO_BASE64_CHARS = 12 * 1024 * 1024
WHISPER_TRANSCRIPTION_TIMEOUT_SECONDS = 45.0


class WhisperTranscriptionRequest(BaseModel):
    """Bounded transcription request accepted by local-core."""

    audio_base64: str = Field(..., min_length=1, max_length=MAX_STT_AUDIO_BASE64_CHARS)
    language: str | None = "auto"
    task: Literal["transcribe", "translate"] = "transcribe"
    model: str = "openai/whisper-medium"
    device: str = "cpu"


@dataclass(frozen=True)
class WhisperTranscriptionResult:
    text: str
    segments: list[dict[str, Any]]
    language: str
    duration: float


class WhisperTranscriptionUnavailable(Exception):
    """Structured unavailable response for Whisper proxy failures."""

    def __init__(
        self,
        *,
        reason: str,
        error: str | None = None,
        upstream_status: int | None = None,
    ) -> None:
        super().__init__(reason)
        self.reason = reason
        self.error = error
        self.upstream_status = upstream_status

    def to_detail(self) -> dict[str, object]:
        detail: dict[str, object] = {"reason": self.reason}
        if self.error:
            detail["error"] = self.error
        if self.upstream_status is not None:
            detail["upstream_status"] = self.upstream_status
        return detail


class WhisperTranscriptionInvalidRequest(Exception):
    """Structured validation response for local STT requests."""

    def __init__(
        self,
        *,
        reason: str,
        message: str,
        max_audio_bytes: int | None = None,
    ) -> None:
        super().__init__(reason)
        self.reason = reason
        self.message = message
        self.max_audio_bytes = max_audio_bytes

    def to_detail(self) -> dict[str, object]:
        detail: dict[str, object] = {
            "reason": self.reason,
            "message": self.message,
        }
        if self.max_audio_bytes is not None:
            detail["max_audio_bytes"] = self.max_audio_bytes
        return detail


def validate_whisper_audio_payload(value: str) -> bytes:
    try:
        audio_bytes = base64.b64decode(value, validate=True)
    except Exception as exc:
        raise WhisperTranscriptionInvalidRequest(
            reason="invalid_audio_base64",
            message="audio_base64 must be valid base64.",
        ) from exc
    if not audio_bytes:
        raise WhisperTranscriptionInvalidRequest(
            reason="empty_audio",
            message="audio_base64 must contain audio bytes.",
        )
    if len(audio_bytes) > MAX_STT_AUDIO_BYTES:
        raise WhisperTranscriptionInvalidRequest(
            reason="audio_too_large",
            message="audio_base64 exceeds the maximum audio byte limit.",
            max_audio_bytes=MAX_STT_AUDIO_BYTES,
        )
    return audio_bytes


def get_whisper_base_url() -> str:
    return os.getenv("WHISPER_SERVICE_URL", DEFAULT_WHISPER_BASE_URL).rstrip("/")


async def transcribe_whisper_audio(
    request: WhisperTranscriptionRequest,
    *,
    base_url: str | None = None,
    timeout_seconds: float = WHISPER_TRANSCRIPTION_TIMEOUT_SECONDS,
) -> WhisperTranscriptionResult:
    """Return a bounded transcript from the Whisper sidecar without persistence."""

    validate_whisper_audio_payload(request.audio_base64)
    endpoint = f"{(base_url or get_whisper_base_url()).rstrip('/')}/transcribe"
    payload = {
        "audio": request.audio_base64,
        "language": request.language or "auto",
        "task": request.task,
        "model": request.model,
        "device": request.device,
    }
    try:
        async with httpx.AsyncClient(timeout=timeout_seconds) as client:
            response = await client.post(endpoint, json=payload)
    except httpx.TimeoutException as exc:
        raise WhisperTranscriptionUnavailable(
            reason="stt_timeout",
            error=str(exc),
        ) from exc
    except httpx.HTTPError as exc:
        raise WhisperTranscriptionUnavailable(
            reason="stt_unreachable",
            error=str(exc),
        ) from exc

    if response.status_code < 200 or response.status_code >= 300:
        raise WhisperTranscriptionUnavailable(
            reason="stt_unavailable",
            error=response.text[:500],
            upstream_status=response.status_code,
        )

    data = response.json()
    return WhisperTranscriptionResult(
        text=str(data.get("text") or ""),
        segments=list(data.get("segments") or []),
        language=str(data.get("language") or "unknown"),
        duration=float(data.get("duration") or 0.0),
    )


__all__ = [
    "DEFAULT_WHISPER_BASE_URL",
    "MAX_STT_AUDIO_BASE64_CHARS",
    "MAX_STT_AUDIO_BYTES",
    "WHISPER_TRANSCRIPTION_TIMEOUT_SECONDS",
    "WhisperTranscriptionInvalidRequest",
    "WhisperTranscriptionRequest",
    "WhisperTranscriptionResult",
    "WhisperTranscriptionUnavailable",
    "get_whisper_base_url",
    "transcribe_whisper_audio",
    "validate_whisper_audio_payload",
]
