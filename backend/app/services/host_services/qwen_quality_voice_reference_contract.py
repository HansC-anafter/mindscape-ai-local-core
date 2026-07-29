"""Authoritative user-accepted reference contract for Qwen quality voice."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
from pathlib import Path
import wave


VOICE_PROFILE_ID = "mms_voice_bilibili_313312170_bv1a2tf64ebd"
VOICE_DISPLAY_NAME = "乘以加"
REFERENCE_CONTRACT_ID = "qwen_cheng_yi_jia_user_accepted_output_quality_v1"
AUTHORITATIVE_REFERENCE_AUDIO_FILENAME = (
    "cheng-yi-jia-authoritative-ed7b564c.wav"
)
AUTHORITATIVE_REFERENCE_AUDIO_SHA256 = (
    "ed7b564c68cde5fea31089c602ae9ea6e5bcfb261a2eea160dd96f05bbcafc82"
)
AUTHORITATIVE_REFERENCE_SOURCE_SHA256 = (
    "7c1d2b380a681433a1f777b541816cde7b83c7a48340b845c4577cb571830e01"
)
AUTHORITATIVE_REFERENCE_TEXT = (
    "還是說回我選的這家吧，進店之後會按照預約的時間給你發一個小牌牌，"
    "我約的是妝面加髮型嘛。"
)
AUTHORITATIVE_REFERENCE_CLIP_START_SECONDS = 2.64
AUTHORITATIVE_REFERENCE_CLIP_END_SECONDS = 10.60
AUTHORITATIVE_REFERENCE_SAMPLE_RATE = 24000
AUTHORITATIVE_REFERENCE_FRAME_COUNT = 191040


class QwenQualityVoiceReferenceError(Exception):
    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


@dataclass(frozen=True)
class ReferenceAudioReceipt:
    sha256: str
    frame_count: int
    sample_rate: int

    @property
    def duration_seconds(self) -> float:
        return self.frame_count / self.sample_rate


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def inspect_authoritative_reference_audio(path: Path) -> ReferenceAudioReceipt:
    """Fail closed unless path is the exact accepted 7.96-second PCM asset."""

    digest = _sha256(path)
    if digest != AUTHORITATIVE_REFERENCE_AUDIO_SHA256:
        raise QwenQualityVoiceReferenceError("reference_audio_digest_mismatch")
    try:
        with wave.open(str(path), "rb") as audio:
            channels = audio.getnchannels()
            sample_width = audio.getsampwidth()
            sample_rate = audio.getframerate()
            frame_count = audio.getnframes()
            compression = audio.getcomptype()
    except (EOFError, wave.Error) as exc:
        raise QwenQualityVoiceReferenceError(
            "reference_audio_format_mismatch"
        ) from exc
    if (
        channels != 1
        or sample_width != 2
        or sample_rate != AUTHORITATIVE_REFERENCE_SAMPLE_RATE
        or frame_count != AUTHORITATIVE_REFERENCE_FRAME_COUNT
        or compression != "NONE"
    ):
        raise QwenQualityVoiceReferenceError("reference_audio_format_mismatch")
    return ReferenceAudioReceipt(
        sha256=digest,
        frame_count=frame_count,
        sample_rate=sample_rate,
    )


__all__ = [
    "AUTHORITATIVE_REFERENCE_AUDIO_FILENAME",
    "AUTHORITATIVE_REFERENCE_AUDIO_SHA256",
    "AUTHORITATIVE_REFERENCE_CLIP_END_SECONDS",
    "AUTHORITATIVE_REFERENCE_CLIP_START_SECONDS",
    "AUTHORITATIVE_REFERENCE_FRAME_COUNT",
    "AUTHORITATIVE_REFERENCE_SAMPLE_RATE",
    "AUTHORITATIVE_REFERENCE_SOURCE_SHA256",
    "AUTHORITATIVE_REFERENCE_TEXT",
    "QwenQualityVoiceReferenceError",
    "REFERENCE_CONTRACT_ID",
    "ReferenceAudioReceipt",
    "VOICE_DISPLAY_NAME",
    "VOICE_PROFILE_ID",
    "inspect_authoritative_reference_audio",
]
