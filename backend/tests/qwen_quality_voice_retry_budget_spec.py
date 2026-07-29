from __future__ import annotations

from array import array
from pathlib import Path
import sys
import wave

from backend.app.services.host_services import qwen_quality_voice_runtime
from backend.app.services.host_services.qwen_quality_voice_output_guard import (
    inspect_pcm16_mono_24khz,
)
from backend.app.services.host_services.qwen_quality_voice_runtime import (
    QualityVoiceRuntime,
    RuntimeConfig,
)
from backend.app.services.host_services.qwen_quality_voice_reference_contract import (
    AUTHORITATIVE_REFERENCE_AUDIO_SHA256,
    ReferenceAudioReceipt,
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


def _config(tmp_path: Path) -> RuntimeConfig:
    runtime_root = tmp_path / "runtime"
    python_bin = runtime_root / "venv" / "bin" / "python"
    model_path = runtime_root / "model"
    reference_audio = runtime_root / "reference" / "selected.wav"
    python_bin.parent.mkdir(parents=True)
    python_bin.write_text("", encoding="utf-8")
    python_bin.chmod(0o700)
    model_path.mkdir()
    reference_audio.parent.mkdir()
    reference_audio.write_bytes(b"RIFF")
    return RuntimeConfig(
        python_bin=python_bin,
        model_path=model_path,
        reference_audio=reference_audio,
        state_dir=tmp_path / "state",
        timeout_seconds=240,
        max_text_chars=700,
        max_tokens=4096,
        max_generation_attempts=2,
    )


def test_clipped_retry_uses_only_remaining_request_budget(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setattr(
        qwen_quality_voice_runtime,
        "inspect_authoritative_reference_audio",
        lambda _path: ReferenceAudioReceipt(
            sha256=AUTHORITATIVE_REFERENCE_AUDIO_SHA256,
            frame_count=191040,
            sample_rate=24000,
        ),
    )
    runtime = QualityVoiceRuntime(_config(tmp_path))
    observed_budgets: list[float] = []

    def _fake_generate_once(
        *,
        text: str,
        language_code: str,
        output_dir: Path,
        file_prefix: str,
        timeout_seconds: float,
    ) -> Path:
        observed_budgets.append(timeout_seconds)
        output = output_dir / f"{file_prefix}.wav"
        if len(observed_budgets) == 1:
            _write_wav(output, [0, 32767, 32767, -32768, 0])
        else:
            _write_wav(output, [0, 18000, -18000, 4000, -4000])
        return output

    monotonic_values = iter([100.0, 101.0, 121.0])
    monkeypatch.setattr(runtime, "_generate_once", _fake_generate_once)
    monkeypatch.setattr(
        qwen_quality_voice_runtime.time,
        "monotonic",
        lambda: next(monotonic_values),
    )

    audio_bytes = runtime.synthesize(text="測試", language_code="Chinese")
    output = tmp_path / "result.wav"
    output.write_bytes(audio_bytes)

    assert observed_budgets == [239.0, 219.0]
    metrics = inspect_pcm16_mono_24khz(output)
    assert metrics.full_scale_sample_count == 0
