"""Deterministic publish gate for Qwen quality-voice PCM output."""

from __future__ import annotations

from array import array
from dataclasses import dataclass
import math
from pathlib import Path
import shutil
import sys
import wave


PCM16_POSITIVE_FULL_SCALE = 32767
PCM16_NEGATIVE_FULL_SCALE = -32768
PUBLISH_SAMPLE_PEAK_DBFS = -2.0
PUBLISH_SAMPLE_PEAK = round(
    PCM16_POSITIVE_FULL_SCALE * (10 ** (PUBLISH_SAMPLE_PEAK_DBFS / 20.0))
)


class QualityVoiceOutputGuardError(Exception):
    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


@dataclass(frozen=True)
class Pcm16WavMetrics:
    frame_count: int
    peak_sample: int
    peak_dbfs: float
    full_scale_sample_count: int


@dataclass(frozen=True)
class QualityVoiceOutputGuardReceipt:
    input_metrics: Pcm16WavMetrics
    output_metrics: Pcm16WavMetrics
    applied_gain: float


def _read_pcm16_mono_24khz(path: Path) -> tuple[wave._wave_params, array[int]]:
    try:
        with wave.open(str(path), "rb") as audio:
            params = audio.getparams()
            if (
                params.nchannels != 1
                or params.sampwidth != 2
                or params.framerate != 24000
                or params.nframes <= 0
                or params.comptype != "NONE"
            ):
                raise QualityVoiceOutputGuardError(
                    "qwen_quality_voice_output_invalid"
                )
            samples = array("h")
            samples.frombytes(audio.readframes(params.nframes))
    except (EOFError, wave.Error) as exc:
        raise QualityVoiceOutputGuardError(
            "qwen_quality_voice_output_invalid"
        ) from exc
    if sys.byteorder != "little":
        samples.byteswap()
    if len(samples) != params.nframes:
        raise QualityVoiceOutputGuardError("qwen_quality_voice_output_invalid")
    return params, samples


def inspect_pcm16_mono_24khz(path: Path) -> Pcm16WavMetrics:
    params, samples = _read_pcm16_mono_24khz(path)
    peak_sample = max(abs(value) for value in samples)
    full_scale_sample_count = sum(
        value in (PCM16_NEGATIVE_FULL_SCALE, PCM16_POSITIVE_FULL_SCALE)
        for value in samples
    )
    peak_dbfs = (
        20.0 * math.log10(peak_sample / 32768.0)
        if peak_sample
        else float("-inf")
    )
    return Pcm16WavMetrics(
        frame_count=params.nframes,
        peak_sample=peak_sample,
        peak_dbfs=peak_dbfs,
        full_scale_sample_count=full_scale_sample_count,
    )


def prepare_publishable_pcm16_wav(
    source_path: Path,
    destination_path: Path,
) -> QualityVoiceOutputGuardReceipt:
    """Reject hard clipping, then apply only downward sample-peak scaling."""

    params, samples = _read_pcm16_mono_24khz(source_path)
    input_metrics = inspect_pcm16_mono_24khz(source_path)
    if input_metrics.full_scale_sample_count > 0:
        raise QualityVoiceOutputGuardError("qwen_quality_voice_output_clipped")

    applied_gain = min(
        1.0,
        PUBLISH_SAMPLE_PEAK / input_metrics.peak_sample
        if input_metrics.peak_sample
        else 1.0,
    )
    temporary_path = destination_path.with_suffix(destination_path.suffix + ".tmp")
    destination_path.parent.mkdir(parents=True, exist_ok=True)
    if applied_gain < 1.0:
        scaled = array(
            "h",
            (
                max(
                    -PUBLISH_SAMPLE_PEAK,
                    min(PUBLISH_SAMPLE_PEAK, round(value * applied_gain)),
                )
                for value in samples
            ),
        )
        if sys.byteorder != "little":
            scaled.byteswap()
        with wave.open(str(temporary_path), "wb") as audio:
            audio.setparams(params)
            audio.writeframes(scaled.tobytes())
    else:
        shutil.copyfile(source_path, temporary_path)
    temporary_path.replace(destination_path)

    output_metrics = inspect_pcm16_mono_24khz(destination_path)
    if output_metrics.full_scale_sample_count > 0:
        raise QualityVoiceOutputGuardError("qwen_quality_voice_output_clipped")
    return QualityVoiceOutputGuardReceipt(
        input_metrics=input_metrics,
        output_metrics=output_metrics,
        applied_gain=applied_gain,
    )


__all__ = [
    "PCM16_NEGATIVE_FULL_SCALE",
    "PCM16_POSITIVE_FULL_SCALE",
    "PUBLISH_SAMPLE_PEAK",
    "PUBLISH_SAMPLE_PEAK_DBFS",
    "Pcm16WavMetrics",
    "QualityVoiceOutputGuardError",
    "QualityVoiceOutputGuardReceipt",
    "inspect_pcm16_mono_24khz",
    "prepare_publishable_pcm16_wav",
]
