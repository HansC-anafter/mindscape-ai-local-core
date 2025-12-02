"""
macOS built-in TTS provider
Uses macOS `say` command or PyObjC for text-to-speech synthesis
"""

import asyncio
import os
import platform
import subprocess
import tempfile
from pathlib import Path
from typing import Optional

from backend.app.shared.audio.tts.base import BaseTTSProvider, TTSError


class MacOSTTSProvider(BaseTTSProvider):
    """macOS TTS provider using system `say` command"""

    def __init__(self):
        self._available_voices: Optional[list[str]] = None

    def is_available(self) -> bool:
        """Check if macOS TTS is available"""
        return platform.system() == "Darwin"

    async def synthesize(
        self,
        text: str,
        language: str = "en",
        voice: Optional[str] = None,
        speed: float = 1.0,
        output_path: Optional[str] = None,
    ) -> str:
        """
        Synthesize speech using macOS `say` command.

        Args:
            text: Text to synthesize
            language: Language code (e.g., "en", "zh-TW")
            voice: Voice name (optional)
            speed: Speech speed (words per minute, adjusted from multiplier)
            output_path: Optional output file path

        Returns:
            Path to generated audio file

        Raises:
            TTSError: If synthesis fails
        """
        if not self.is_available():
            raise TTSError("macOS TTS is only available on macOS systems")

        if not output_path:
            output_dir = Path(tempfile.gettempdir()) / "mindscape_tts"
            output_dir.mkdir(exist_ok=True)
            output_path = str(output_dir / f"tts_{os.getpid()}_{id(text)}.aiff")

        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)

        cmd = ["say", "-o", str(output_path)]

        if voice:
            cmd.extend(["-v", voice])
        elif language:
            cmd.extend(["-v", self._get_default_voice_for_language(language)])

        if speed != 1.0:
            wpm = int(175 * speed)
            cmd.extend(["-r", str(wpm)])

        cmd.append(text)

        try:
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await process.communicate()

            if process.returncode != 0:
                error_msg = stderr.decode() if stderr else "Unknown error"
                raise TTSError(f"TTS synthesis failed: {error_msg}")

            if not output_path.exists():
                raise TTSError(f"Output file was not created: {output_path}")

            return str(output_path)

        except FileNotFoundError:
            raise TTSError("macOS `say` command not found")
        except Exception as e:
            raise TTSError(f"TTS synthesis error: {str(e)}")

    def _get_default_voice_for_language(self, language: str) -> str:
        """Get default voice for language code"""
        language_voice_map = {
            "en": "Alex",
            "en-US": "Alex",
            "en-GB": "Daniel",
            "zh-TW": "Ting-Ting",
            "zh-CN": "Ting-Ting",
            "zh": "Ting-Ting",
            "ja": "Kyoko",
            "ko": "Yuna",
            "es": "Monica",
            "fr": "Thomas",
            "de": "Anna",
            "it": "Alice",
            "pt": "Luciana",
        }

        return language_voice_map.get(language, "Alex")

    def get_available_voices(self, language: Optional[str] = None) -> list[str]:
        """
        Get list of available voices.

        Args:
            language: Optional language code to filter voices

        Returns:
            List of voice names
        """
        if not self.is_available():
            return []

        if self._available_voices is None:
            try:
                result = subprocess.run(
                    ["say", "-v", "?"],
                    capture_output=True,
                    text=True,
                    timeout=5,
                )
                if result.returncode == 0:
                    voices = []
                    for line in result.stdout.strip().split("\n"):
                        if line.strip():
                            voice_name = line.split()[0] if line.split() else ""
                            if voice_name:
                                voices.append(voice_name)
                    self._available_voices = voices
                else:
                    self._available_voices = []
            except Exception:
                self._available_voices = []

        if language:
            filtered_voices = []
            for voice in self._available_voices:
                result = subprocess.run(
                    ["say", "-v", voice, "test"],
                    capture_output=True,
                    text=True,
                    timeout=2,
                )
                if result.returncode == 0:
                    filtered_voices.append(voice)
            return filtered_voices

        return self._available_voices or []
