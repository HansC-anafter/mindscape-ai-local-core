"""
Speech-to-Text (STT) providers
Unified interface for STT implementations
"""

__all__ = ["BaseSTTProvider", "get_stt_provider"]

from backend.app.shared.audio.stt.base import BaseSTTProvider
from backend.app.shared.audio.stt.factory import get_stt_provider
