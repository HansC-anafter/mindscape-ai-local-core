"""
Whisper STT provider
Uses OpenAI Whisper or whisper.cpp for speech-to-text transcription
"""

import asyncio
import os
import platform
from pathlib import Path
from typing import Optional, Any

from backend.app.shared.audio.stt.base import BaseSTTProvider, STTError


class WhisperSTTProvider(BaseSTTProvider):
    """Whisper STT provider using OpenAI Whisper model"""

    def __init__(self, model_size: str = "base"):
        """
        Initialize Whisper STT provider.

        Args:
            model_size: Model size ("tiny", "base", "small", "medium", "large")
        """
        self.model_size = model_size
        self._model = None
        self._initialized = False

    def _ensure_initialized(self):
        """Ensure Whisper model is loaded"""
        if self._initialized:
            return

        try:
            import whisper

            self._model = whisper.load_model(self.model_size)
            self._initialized = True
        except ImportError:
            raise STTError(
                "Whisper library not installed. Install with: pip install openai-whisper"
            )
        except Exception as e:
            raise STTError(f"Failed to load Whisper model: {str(e)}")

    def is_available(self) -> bool:
        """Check if Whisper STT is available"""
        try:
            import whisper

            return True
        except ImportError:
            return False

    async def transcribe(
        self,
        audio_path: str,
        language: Optional[str] = None,
        task: str = "transcribe",
    ) -> dict[str, Any]:
        """
        Transcribe audio file using Whisper.

        Args:
            audio_path: Path to audio file
            language: Optional language code (auto-detect if not provided)
            task: Task type - "transcribe" or "translate"

        Returns:
            Dictionary with transcription results

        Raises:
            STTError: If transcription fails
        """
        if not self.is_available():
            raise STTError("Whisper STT is not available")

        if not os.path.exists(audio_path):
            raise STTError(f"Audio file not found: {audio_path}")

        self._ensure_initialized()

        try:
            import whisper

            options = {
                "language": language if language else None,
                "task": task,
            }

            result = await asyncio.to_thread(self._model.transcribe, audio_path, **options)

            segments = []
            for segment in result.get("segments", []):
                segments.append(
                    {
                        "text": segment.get("text", "").strip(),
                        "start": segment.get("start", 0.0),
                        "end": segment.get("end", 0.0),
                        "confidence": segment.get("no_speech_prob", 1.0),
                    }
                )

            return {
                "text": result.get("text", "").strip(),
                "language": result.get("language", language or "unknown"),
                "segments": segments,
                "confidence": 1.0 - result.get("no_speech_prob", 0.0),
            }

        except Exception as e:
            raise STTError(f"Transcription failed: {str(e)}")

    def get_supported_languages(self) -> list[str]:
        """
        Get list of supported language codes.

        Returns:
            List of language codes supported by Whisper
        """
        return [
            "en",
            "zh",
            "de",
            "es",
            "ru",
            "ko",
            "fr",
            "ja",
            "pt",
            "tr",
            "pl",
            "ca",
            "nl",
            "ar",
            "sv",
            "it",
            "id",
            "hi",
            "fi",
            "vi",
            "he",
            "uk",
            "el",
            "ms",
            "cs",
            "ro",
            "da",
            "hu",
            "ta",
            "no",
            "th",
            "ur",
            "hr",
            "bg",
            "lt",
            "la",
            "mi",
            "ml",
            "cy",
            "sk",
            "te",
            "fa",
            "lv",
            "bn",
            "sr",
            "az",
            "sl",
            "kn",
            "et",
            "mk",
            "br",
            "eu",
            "is",
            "hy",
            "ne",
            "mn",
            "bs",
            "kk",
            "sq",
            "sw",
            "gl",
            "mr",
            "pa",
            "si",
            "km",
            "sn",
            "yo",
            "so",
            "af",
            "oc",
            "ka",
            "be",
            "tg",
            "sd",
            "gu",
            "am",
            "yi",
            "lo",
            "uz",
            "fo",
            "ht",
            "ps",
            "tk",
            "nn",
            "mt",
            "sa",
            "lb",
            "my",
            "bo",
            "tl",
            "mg",
            "as",
            "tt",
            "haw",
            "ln",
            "ha",
            "ba",
            "jw",
            "su",
        ]
