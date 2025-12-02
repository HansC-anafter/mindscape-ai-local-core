"""
Base STT provider interface
Defines the unified interface for all STT implementations
"""

from abc import ABC, abstractmethod
from typing import Optional, Any


class STTError(Exception):
    """Base exception for STT errors"""

    pass


class BaseSTTProvider(ABC):
    """Abstract base class for STT providers"""

    @abstractmethod
    async def transcribe(
        self,
        audio_path: str,
        language: Optional[str] = None,
        task: str = "transcribe",
    ) -> dict[str, Any]:
        """
        Transcribe audio file to text.

        Args:
            audio_path: Path to audio file
            language: Optional language code (auto-detect if not provided)
            task: Task type - "transcribe" or "translate"

        Returns:
            Dictionary containing:
                - text: Transcribed text
                - language: Detected language code
                - segments: List of segments with timestamps
                - confidence: Overall confidence score

        Raises:
            STTError: If transcription fails
        """
        pass

    @abstractmethod
    def is_available(self) -> bool:
        """
        Check if this STT provider is available on the current system.

        Returns:
            True if available, False otherwise
        """
        pass

    @abstractmethod
    def get_supported_languages(self) -> list[str]:
        """
        Get list of supported language codes.

        Returns:
            List of language codes (e.g., ["en", "zh", "ja"])
        """
        pass
