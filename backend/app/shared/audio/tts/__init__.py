"""
Text-to-Speech (TTS) providers
Unified interface for TTS implementations
"""

__all__ = ["BaseTTSProvider", "get_tts_provider"]

from backend.app.shared.audio.tts.base import BaseTTSProvider
from backend.app.shared.audio.tts.factory import get_tts_provider
