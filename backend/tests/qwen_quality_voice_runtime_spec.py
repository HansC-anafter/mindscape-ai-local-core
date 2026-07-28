from __future__ import annotations

from http import HTTPStatus
from pathlib import Path

import pytest

from backend.app.services.host_services.qwen_quality_voice_runtime import (
    PROVIDER_ID,
    VOICE_DISPLAY_NAME,
    VOICE_PROFILE_ID,
    QualityVoiceRequestError,
    QualityVoiceRuntime,
    RuntimeConfig,
    build_generation_argv,
    parse_synthesis_payload,
)


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
        reference_text="參考文字",
        state_dir=tmp_path / "state",
        timeout_seconds=240,
        max_text_chars=700,
        max_tokens=4096,
        max_generation_attempts=2,
    )


def test_health_exposes_selected_non_realtime_provider(tmp_path: Path) -> None:
    health = QualityVoiceRuntime(_config(tmp_path)).health()

    assert health == {
        "status": "ok",
        "reason": None,
        "provider": PROVIDER_ID,
        "voice_profile_id": VOICE_PROFILE_ID,
        "voice_display_name": VOICE_DISPLAY_NAME,
        "quality_lane": "asynchronous_high_quality",
        "realtime": False,
        "fallback": None,
        "busy": False,
        "output_guard": "reject_clipping_retry_once_then_minus_2_dbfs",
        "max_generation_attempts": 2,
    }


def test_payload_defaults_to_selected_profile_and_chinese(tmp_path: Path) -> None:
    text, language = parse_synthesis_payload(
        {"text": "現在開始播放。", "output_format": "wav"}, _config(tmp_path)
    )

    assert text == "現在開始播放。"
    assert language == "Chinese"


def test_payload_rejects_other_voice_profile(tmp_path: Path) -> None:
    with pytest.raises(QualityVoiceRequestError) as raised:
        parse_synthesis_payload(
            {"text": "test", "voice_profile_id": "other"}, _config(tmp_path)
        )

    assert raised.value.status == HTTPStatus.CONFLICT
    assert raised.value.reason == "voice_profile_not_available"


def test_generation_command_is_offline_pinned_quality_configuration(
    tmp_path: Path,
) -> None:
    config = _config(tmp_path)
    argv = build_generation_argv(
        config,
        text="品質測試",
        language_code="Chinese",
        output_dir=tmp_path / "output",
        file_prefix="speech",
    )

    assert argv[0] == str(config.python_bin)
    assert argv[argv.index("--model") + 1] == str(config.model_path)
    assert argv[argv.index("--ref_audio") + 1] == str(config.reference_audio)
    assert argv[argv.index("--temperature") + 1] == "0.7"
    assert argv[argv.index("--top_p") + 1] == "0.9"
    assert argv[argv.index("--max_tokens") + 1] == "4096"
    assert "--join_audio" in argv
