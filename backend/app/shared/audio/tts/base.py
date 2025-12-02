"""
Base TTS provider interface
Defines the unified interface for all TTS implementations
"""

from abc import ABC, abstractmethod
from typing import Optional


class TTSError(Exception):
    """Base exception for TTS errors"""

    pass


class BaseTTSProvider(ABC):
    """Abstract base class for TTS providers"""

    @abstractmethod
    async def synthesize(
        self,
        text: str,
        language: str = "en",
        voice: Optional[str] = None,
        speed: float = 1.0,
        output_path: Optional[str] = None,
    ) -> str:
        """
        Synthesize speech from text.

        Args:
            text: Text to synthesize
            language: Language code (e.g., "en", "zh-TW")
            voice: Voice name (optional, uses system default if not provided)
            speed: Speech speed multiplier (1.0 = normal speed)
            output_path: Optional output file path

        Returns:
            Path to generated audio file

        Raises:
            TTSError: If synthesis fails
        """
        pass

    @abstractmethod
    def get_available_voices(self, language: Optional[str] = None) -> list[str]:
        """
        Get list of available voices.

        Args:
            language: Optional language code to filter voices

        Returns:
            List of voice names
        """
        pass

    @abstractmethod
    def is_available(self) -> bool:
        """
        Check if this TTS provider is available on the current system.

        Returns:
            True if available, False otherwise
        """
        pass
