"""Single provider facade for Local Core asynchronous quality speech."""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Literal

import httpx
from pydantic import BaseModel, Field


DEFAULT_QUALITY_VOICE_BASE_URL = "http://host.docker.internal:8184"
DEFAULT_QUALITY_VOICE_PROFILE_ID = "mms_voice_bilibili_313312170_bv1a2tf64ebd"
MAX_QUALITY_VOICE_TEXT_CHARS = 700
QUALITY_VOICE_SYNTHESIS_TIMEOUT_SECONDS = 240.0
QUALITY_VOICE_SUPPORTED_LANGUAGES = {
    "en",
    "es",
    "fr",
    "de",
    "it",
    "pt",
    "ru",
    "zh-cn",
    "ko",
    "ja",
}
QUALITY_VOICE_LANGUAGE_ALIASES = {
    "zh": "zh-cn",
    "zh-cn": "zh-cn",
    "zh-hans": "zh-cn",
    "zh-hans-cn": "zh-cn",
    "zh-hant": "zh-cn",
    "zh-hant-tw": "zh-cn",
    "zh-tw": "zh-cn",
    "zh-hk": "zh-cn",
    "zh-mo": "zh-cn",
}


class QualityVoiceSynthesisRequest(BaseModel):
    """Bounded request for the preselected asynchronous quality voice."""

    text: str = Field(..., min_length=1, max_length=MAX_QUALITY_VOICE_TEXT_CHARS)
    language: str = "zh-cn"
    voice_profile_id: str | None = DEFAULT_QUALITY_VOICE_PROFILE_ID
    output_format: Literal["wav"] = "wav"


@dataclass(frozen=True)
class QualityVoiceAudioResult:
    audio_bytes: bytes
    media_type: str


class QualityVoiceUnavailable(Exception):
    """Structured unavailable response from the sole Qwen quality provider."""

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


def get_quality_voice_base_url() -> str:
    return os.getenv(
        "QWEN_QUALITY_VOICE_SERVICE_URL", DEFAULT_QUALITY_VOICE_BASE_URL
    ).rstrip("/")


def get_quality_voice_synthesis_timeout_seconds() -> float:
    raw_value = os.getenv("QWEN_QUALITY_VOICE_SYNTHESIS_TIMEOUT_SECONDS", "").strip()
    if not raw_value:
        return QUALITY_VOICE_SYNTHESIS_TIMEOUT_SECONDS
    try:
        parsed = float(raw_value)
    except ValueError:
        return QUALITY_VOICE_SYNTHESIS_TIMEOUT_SECONDS
    return parsed if parsed > 0 else QUALITY_VOICE_SYNTHESIS_TIMEOUT_SECONDS


def normalize_quality_voice_language(language: str) -> str:
    normalized = str(language or "").strip().lower().replace("_", "-")
    if not normalized:
        return "zh-cn"
    alias = QUALITY_VOICE_LANGUAGE_ALIASES.get(normalized)
    if alias:
        return alias
    if normalized in QUALITY_VOICE_SUPPORTED_LANGUAGES:
        return normalized
    base_language = normalized.split("-", 1)[0]
    if base_language in QUALITY_VOICE_SUPPORTED_LANGUAGES:
        return base_language
    return normalized


async def synthesize_quality_voice_audio(
    request: QualityVoiceSynthesisRequest,
    *,
    base_url: str | None = None,
    timeout_seconds: float | None = None,
) -> QualityVoiceAudioResult:
    """Return Qwen audio bytes without persistence or provider fallback."""

    endpoint = f"{(base_url or get_quality_voice_base_url()).rstrip('/')}/tts"
    effective_timeout_seconds = (
        timeout_seconds
        if timeout_seconds is not None and timeout_seconds > 0
        else get_quality_voice_synthesis_timeout_seconds()
    )
    payload = {
        "text": request.text.strip(),
        "language": normalize_quality_voice_language(request.language),
        "voice_profile_id": request.voice_profile_id
        or DEFAULT_QUALITY_VOICE_PROFILE_ID,
        "output_format": request.output_format,
    }
    try:
        async with httpx.AsyncClient(timeout=effective_timeout_seconds) as client:
            response = await client.post(endpoint, json=payload)
    except httpx.TimeoutException as exc:
        raise QualityVoiceUnavailable(
            reason="qwen_quality_voice_timeout", error=str(exc)
        ) from exc
    except httpx.HTTPError as exc:
        raise QualityVoiceUnavailable(
            reason="qwen_quality_voice_unreachable", error=str(exc)
        ) from exc

    if response.status_code < 200 or response.status_code >= 300:
        upstream_reason = ""
        try:
            body = response.json()
            if isinstance(body, dict):
                upstream_reason = str(body.get("reason") or "")
        except ValueError:
            pass
        raise QualityVoiceUnavailable(
            reason=upstream_reason or "qwen_quality_voice_unavailable",
            error=response.text[:500],
            upstream_status=response.status_code,
        )

    media_type = response.headers.get("content-type") or "audio/wav"
    return QualityVoiceAudioResult(audio_bytes=response.content, media_type=media_type)


__all__ = [
    "DEFAULT_QUALITY_VOICE_BASE_URL",
    "DEFAULT_QUALITY_VOICE_PROFILE_ID",
    "MAX_QUALITY_VOICE_TEXT_CHARS",
    "QUALITY_VOICE_SYNTHESIS_TIMEOUT_SECONDS",
    "QualityVoiceAudioResult",
    "QualityVoiceSynthesisRequest",
    "QualityVoiceUnavailable",
    "get_quality_voice_base_url",
    "get_quality_voice_synthesis_timeout_seconds",
    "normalize_quality_voice_language",
    "synthesize_quality_voice_audio",
]
