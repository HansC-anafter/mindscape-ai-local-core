"""
STT provider factory
Returns appropriate STT provider based on system capabilities
"""

from typing import Optional

from backend.app.shared.audio.stt.base import BaseSTTProvider
from backend.app.shared.audio.stt.whisper_stt import WhisperSTTProvider

_stt_provider: Optional[BaseSTTProvider] = None


def get_stt_provider() -> BaseSTTProvider:
    """
    Get the appropriate STT provider for the current system.

    Returns:
        STT provider instance

    Raises:
        RuntimeError: If no STT provider is available
    """
    global _stt_provider

    if _stt_provider is not None:
        return _stt_provider

    provider = WhisperSTTProvider()
    if provider.is_available():
        _stt_provider = provider
        return _stt_provider

    raise RuntimeError("No STT provider is available on this system")
