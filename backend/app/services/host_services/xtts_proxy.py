"""Compatibility aliases for the retired XTTS route name.

All synthesis is delegated to the sole Qwen quality-voice facade. There is no
XTTS or F5 fallback behind these aliases.
"""

from backend.app.services.host_services.quality_voice_facade import (
    DEFAULT_QUALITY_VOICE_BASE_URL,
    MAX_QUALITY_VOICE_TEXT_CHARS,
    QUALITY_VOICE_SYNTHESIS_TIMEOUT_SECONDS,
    QualityVoiceAudioResult,
    QualityVoiceSynthesisRequest,
    QualityVoiceUnavailable,
    get_quality_voice_base_url,
    get_quality_voice_synthesis_timeout_seconds,
    normalize_quality_voice_language,
    synthesize_quality_voice_audio,
)

DEFAULT_XTTS_BASE_URL = DEFAULT_QUALITY_VOICE_BASE_URL
MAX_TTS_TEXT_CHARS = MAX_QUALITY_VOICE_TEXT_CHARS
XTTS_SYNTHESIS_TIMEOUT_SECONDS = QUALITY_VOICE_SYNTHESIS_TIMEOUT_SECONDS
XTTSAudioResult = QualityVoiceAudioResult
XTTSSynthesisRequest = QualityVoiceSynthesisRequest
XTTSSynthesisUnavailable = QualityVoiceUnavailable
get_xtts_base_url = get_quality_voice_base_url
get_xtts_synthesis_timeout_seconds = get_quality_voice_synthesis_timeout_seconds
normalize_xtts_language = normalize_quality_voice_language
synthesize_xtts_audio = synthesize_quality_voice_audio

__all__ = [
    "DEFAULT_XTTS_BASE_URL",
    "MAX_TTS_TEXT_CHARS",
    "XTTS_SYNTHESIS_TIMEOUT_SECONDS",
    "XTTSAudioResult",
    "XTTSSynthesisRequest",
    "XTTSSynthesisUnavailable",
    "get_xtts_base_url",
    "get_xtts_synthesis_timeout_seconds",
    "normalize_xtts_language",
    "synthesize_xtts_audio",
]
