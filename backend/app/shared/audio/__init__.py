"""
Shared audio processing layer
Provides unified interfaces for TTS and STT implementations
"""

__all__ = ["get_tts_provider", "get_stt_provider"]

from backend.app.shared.audio.tts import get_tts_provider
from backend.app.shared.audio.stt import get_stt_provider
