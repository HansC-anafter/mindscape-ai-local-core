from __future__ import annotations

from array import array
from pathlib import Path
import sys
import wave

import pytest

from backend.app.services.host_services.qwen_quality_voice_output_guard import (
    PUBLISH_SAMPLE_PEAK,
    QualityVoiceOutputGuardError,
    inspect_pcm16_mono_24khz,
    prepare_publishable_pcm16_wav,
)


def _write_wav(path: Path, samples: list[int]) -> None:
    values = array("h", samples)
    if sys.byteorder != "little":
        values.byteswap()
    with wave.open(str(path), "wb") as audio:
        audio.setnchannels(1)
        audio.setsampwidth(2)
        audio.setframerate(24000)
        audio.writeframes(values.tobytes())


def test_rejects_any_full_scale_sample(tmp_path: Path) -> None:
    source = tmp_path / "clipped.wav"
    _write_wav(source, [0, 1200, 32767, 32767, -32768, -800])

    with pytest.raises(QualityVoiceOutputGuardError) as raised:
        prepare_publishable_pcm16_wav(source, tmp_path / "publishable.wav")

    assert raised.value.reason == "qwen_quality_voice_output_clipped"
    assert not (tmp_path / "publishable.wav").exists()


def test_scales_only_down_to_publish_sample_peak(tmp_path: Path) -> None:
    source = tmp_path / "hot.wav"
    destination = tmp_path / "publishable.wav"
    _write_wav(source, [0, 32000, -32000, 1000, -1000])

    receipt = prepare_publishable_pcm16_wav(source, destination)

    assert 0 < receipt.applied_gain < 1
    assert receipt.input_metrics.peak_sample == 32000
    assert receipt.output_metrics.peak_sample <= PUBLISH_SAMPLE_PEAK
    assert receipt.output_metrics.full_scale_sample_count == 0


def test_preserves_already_safe_pcm(tmp_path: Path) -> None:
    source = tmp_path / "safe.wav"
    destination = tmp_path / "publishable.wav"
    _write_wav(source, [0, 2000, -4000, 8000, -12000])

    receipt = prepare_publishable_pcm16_wav(source, destination)

    assert receipt.applied_gain == 1.0
    assert destination.read_bytes() == source.read_bytes()
    assert inspect_pcm16_mono_24khz(destination).full_scale_sample_count == 0
