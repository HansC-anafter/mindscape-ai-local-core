"""Proxy XTTS synthesis requests to the local sidecar service."""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Literal

import httpx
from pydantic import BaseModel, Field


DEFAULT_XTTS_BASE_URL = "http://xtts-service:8020"
MAX_TTS_TEXT_CHARS = 700
XTTS_SYNTHESIS_TIMEOUT_SECONDS = 20.0


class XTTSSynthesisRequest(BaseModel):
    """Bounded XTTS synthesis request."""

    text: str = Field(..., min_length=1, max_length=MAX_TTS_TEXT_CHARS)
    language: str = "zh-cn"
    voice_profile_id: str | None = None
    output_format: Literal["wav", "mp3"] = "wav"


@dataclass(frozen=True)
class XTTSAudioResult:
    audio_bytes: bytes
    media_type: str


class XTTSSynthesisUnavailable(Exception):
    """Structured unavailable response for XTTS proxy failures."""

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


def get_xtts_base_url() -> str:
    return os.getenv("XTTS_SERVICE_URL", DEFAULT_XTTS_BASE_URL).rstrip("/")


async def synthesize_xtts_audio(
    request: XTTSSynthesisRequest,
    *,
    base_url: str | None = None,
    timeout_seconds: float = XTTS_SYNTHESIS_TIMEOUT_SECONDS,
) -> XTTSAudioResult:
    """Return audio bytes from the XTTS sidecar without persistence."""

    endpoint = f"{(base_url or get_xtts_base_url()).rstrip('/')}/tts"
    payload = {
        "text": request.text.strip(),
        "language": request.language,
        "voice_profile_id": request.voice_profile_id,
        "output_format": request.output_format,
    }
    try:
        async with httpx.AsyncClient(timeout=timeout_seconds) as client:
            response = await client.post(endpoint, json=payload)
    except httpx.TimeoutException as exc:
        raise XTTSSynthesisUnavailable(reason="xtts_timeout", error=str(exc)) from exc
    except httpx.HTTPError as exc:
        raise XTTSSynthesisUnavailable(reason="xtts_unreachable", error=str(exc)) from exc

    if response.status_code < 200 or response.status_code >= 300:
        raise XTTSSynthesisUnavailable(
            reason="xtts_unavailable",
            error=response.text[:500],
            upstream_status=response.status_code,
        )

    media_type = response.headers.get("content-type")
    if not media_type:
        media_type = "audio/mpeg" if request.output_format == "mp3" else "audio/wav"
    return XTTSAudioResult(audio_bytes=response.content, media_type=media_type)


__all__ = [
    "DEFAULT_XTTS_BASE_URL",
    "MAX_TTS_TEXT_CHARS",
    "XTTS_SYNTHESIS_TIMEOUT_SECONDS",
    "XTTSAudioResult",
    "XTTSSynthesisRequest",
    "XTTSSynthesisUnavailable",
    "get_xtts_base_url",
    "synthesize_xtts_audio",
]
