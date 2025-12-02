"""
TTS provider factory
Returns appropriate TTS provider based on system capabilities
"""

import platform
from typing import Optional

from backend.app.shared.audio.tts.base import BaseTTSProvider
from backend.app.shared.audio.tts.macos_tts import MacOSTTSProvider

_tts_provider: Optional[BaseTTSProvider] = None


def get_tts_provider() -> BaseTTSProvider:
    """
    Get the appropriate TTS provider for the current system.

    Returns:
        TTS provider instance

    Raises:
        RuntimeError: If no TTS provider is available
    """
    global _tts_provider

    if _tts_provider is not None:
        return _tts_provider

    if platform.system() == "Darwin":
        provider = MacOSTTSProvider()
        if provider.is_available():
            _tts_provider = provider
            return _tts_provider

    raise RuntimeError("No TTS provider is available on this system")
