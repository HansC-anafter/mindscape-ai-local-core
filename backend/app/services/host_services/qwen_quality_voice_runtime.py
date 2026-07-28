"""Bounded macOS host runtime for Qwen3-TTS Base bf16 quality synthesis."""

from __future__ import annotations

import argparse
import json
import os
import signal
import subprocess
import tempfile
import threading
import wave
from dataclasses import dataclass
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Mapping


PROVIDER_ID = "qwen3_tts_0_6b_base_bf16"
VOICE_PROFILE_ID = "mms_voice_bilibili_313312170_bv1a2tf64ebd"
VOICE_DISPLAY_NAME = "乘以加"
DEFAULT_REFERENCE_TEXT = "我約的是妝面加髮型嘛，所以會先帶去洗個頭。"
LANGUAGE_CODES = {
    "zh": "Chinese",
    "zh-cn": "Chinese",
    "zh-hans": "Chinese",
    "zh-hant": "Chinese",
    "zh-tw": "Chinese",
    "en": "English",
    "es": "Spanish",
    "fr": "French",
    "de": "German",
    "it": "Italian",
    "pt": "Portuguese",
    "ru": "Russian",
    "ko": "Korean",
    "ja": "Japanese",
}


class QualityVoiceRequestError(Exception):
    def __init__(self, status: int, reason: str) -> None:
        super().__init__(reason)
        self.status = status
        self.reason = reason


class QualityVoiceRuntimeError(Exception):
    def __init__(self, status: int, reason: str) -> None:
        super().__init__(reason)
        self.status = status
        self.reason = reason


@dataclass(frozen=True)
class RuntimeConfig:
    python_bin: Path
    model_path: Path
    reference_audio: Path
    reference_text: str
    state_dir: Path
    timeout_seconds: float
    max_text_chars: int
    max_tokens: int

    @classmethod
    def from_env(cls, env: Mapping[str, str] | None = None) -> "RuntimeConfig":
        source = env or os.environ
        runtime_root = Path(source.get("QWEN_QUALITY_RUNTIME_ROOT", "")).expanduser()
        if not str(runtime_root):
            raise ValueError("QWEN_QUALITY_RUNTIME_ROOT is required")
        reference_audio = Path(
            source.get(
                "QWEN_QUALITY_REFERENCE_AUDIO",
                str(runtime_root / "reference" / "cheng-yi-jia-selected.wav"),
            )
        ).expanduser()
        return cls(
            python_bin=runtime_root / "venv" / "bin" / "python",
            model_path=runtime_root / "model",
            reference_audio=reference_audio,
            reference_text=source.get(
                "QWEN_QUALITY_REFERENCE_TEXT", DEFAULT_REFERENCE_TEXT
            ).strip()
            or DEFAULT_REFERENCE_TEXT,
            state_dir=Path(
                source.get(
                    "QWEN_QUALITY_STATE_DIR",
                    str(Path.home() / ".mindscape" / "qwen-quality-voice"),
                )
            ).expanduser(),
            timeout_seconds=float(
                source.get("QWEN_QUALITY_GENERATION_TIMEOUT_SECONDS", "240")
            ),
            max_text_chars=int(source.get("QWEN_QUALITY_MAX_TEXT_CHARS", "700")),
            max_tokens=int(source.get("QWEN_QUALITY_MAX_TOKENS", "4096")),
        )

    def readiness_error(self) -> str | None:
        checks = (
            (self.python_bin.is_file() and os.access(self.python_bin, os.X_OK), "python_missing"),
            (self.model_path.is_dir(), "model_missing"),
            (self.reference_audio.is_file(), "reference_audio_missing"),
            (bool(self.reference_text), "reference_text_missing"),
            (self.timeout_seconds > 0, "invalid_timeout"),
            (self.max_text_chars > 0, "invalid_text_limit"),
            (self.max_tokens > 0, "invalid_token_limit"),
        )
        for valid, reason in checks:
            if not valid:
                return reason
        return None


def normalize_language(value: str) -> str:
    normalized = str(value or "zh-cn").strip().lower().replace("_", "-")
    if normalized in LANGUAGE_CODES:
        return LANGUAGE_CODES[normalized]
    base = normalized.split("-", 1)[0]
    if base in LANGUAGE_CODES:
        return LANGUAGE_CODES[base]
    raise QualityVoiceRequestError(HTTPStatus.UNPROCESSABLE_ENTITY, "unsupported_language")


def parse_synthesis_payload(payload: object, config: RuntimeConfig) -> tuple[str, str]:
    if not isinstance(payload, dict):
        raise QualityVoiceRequestError(HTTPStatus.BAD_REQUEST, "invalid_json_body")
    text = str(payload.get("text") or "").strip()
    if not text:
        raise QualityVoiceRequestError(HTTPStatus.UNPROCESSABLE_ENTITY, "text_required")
    if len(text) > config.max_text_chars:
        raise QualityVoiceRequestError(HTTPStatus.UNPROCESSABLE_ENTITY, "text_too_long")
    profile_id = payload.get("voice_profile_id") or VOICE_PROFILE_ID
    if profile_id != VOICE_PROFILE_ID:
        raise QualityVoiceRequestError(
            HTTPStatus.CONFLICT, "voice_profile_not_available"
        )
    if payload.get("output_format", "wav") != "wav":
        raise QualityVoiceRequestError(
            HTTPStatus.UNPROCESSABLE_ENTITY, "wav_output_required"
        )
    return text, normalize_language(str(payload.get("language") or "zh-cn"))


def build_generation_argv(
    config: RuntimeConfig,
    *,
    text: str,
    language_code: str,
    output_dir: Path,
    file_prefix: str,
) -> list[str]:
    return [
        str(config.python_bin),
        "-m",
        "mlx_audio.tts.generate",
        "--model",
        str(config.model_path),
        "--text",
        text,
        "--lang_code",
        language_code,
        "--ref_audio",
        str(config.reference_audio),
        "--ref_text",
        config.reference_text,
        "--temperature",
        "0.7",
        "--top_k",
        "50",
        "--top_p",
        "0.9",
        "--repetition_penalty",
        "1.05",
        "--max_tokens",
        str(config.max_tokens),
        "--audio_format",
        "wav",
        "--output_path",
        str(output_dir),
        "--file_prefix",
        file_prefix,
        "--join_audio",
    ]


def terminate_process_group(process: subprocess.Popen[bytes]) -> None:
    if process.poll() is not None:
        return
    try:
        os.killpg(process.pid, signal.SIGTERM)
        process.wait(timeout=5)
    except (ProcessLookupError, subprocess.TimeoutExpired):
        if process.poll() is None:
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            process.wait(timeout=5)


class QualityVoiceRuntime:
    def __init__(self, config: RuntimeConfig) -> None:
        self.config = config
        self._generation_lock = threading.Lock()
        self._process_lock = threading.Lock()
        self._active_process: subprocess.Popen[bytes] | None = None

    @property
    def busy(self) -> bool:
        return self._generation_lock.locked()

    def health(self) -> dict[str, object]:
        readiness_error = self.config.readiness_error()
        return {
            "status": "ok" if readiness_error is None else "unavailable",
            "reason": readiness_error,
            "provider": PROVIDER_ID,
            "voice_profile_id": VOICE_PROFILE_ID,
            "voice_display_name": VOICE_DISPLAY_NAME,
            "quality_lane": "asynchronous_high_quality",
            "realtime": False,
            "fallback": None,
            "busy": self.busy,
        }

    def synthesize(self, *, text: str, language_code: str) -> bytes:
        readiness_error = self.config.readiness_error()
        if readiness_error:
            raise QualityVoiceRuntimeError(
                HTTPStatus.SERVICE_UNAVAILABLE, readiness_error
            )
        if not self._generation_lock.acquire(blocking=False):
            raise QualityVoiceRuntimeError(
                HTTPStatus.CONFLICT, "qwen_quality_voice_busy"
            )
        try:
            self.config.state_dir.mkdir(parents=True, exist_ok=True)
            with tempfile.TemporaryDirectory(
                prefix="job-", dir=self.config.state_dir
            ) as temporary:
                output_dir = Path(temporary)
                output_wav = output_dir / "speech.wav"
                log_path = output_dir / "generation.log"
                argv = build_generation_argv(
                    self.config,
                    text=text,
                    language_code=language_code,
                    output_dir=output_dir,
                    file_prefix="speech",
                )
                environment = dict(os.environ)
                environment.update(
                    {
                        "HF_HUB_OFFLINE": "1",
                        "TRANSFORMERS_OFFLINE": "1",
                        "HF_DATASETS_OFFLINE": "1",
                        "TOKENIZERS_PARALLELISM": "false",
                    }
                )
                with log_path.open("wb") as log:
                    process = subprocess.Popen(
                        argv,
                        stdout=log,
                        stderr=subprocess.STDOUT,
                        env=environment,
                        start_new_session=True,
                    )
                    with self._process_lock:
                        self._active_process = process
                    try:
                        return_code = process.wait(
                            timeout=self.config.timeout_seconds
                        )
                    except subprocess.TimeoutExpired as exc:
                        terminate_process_group(process)
                        raise QualityVoiceRuntimeError(
                            HTTPStatus.GATEWAY_TIMEOUT,
                            "qwen_quality_voice_timeout",
                        ) from exc
                    finally:
                        with self._process_lock:
                            self._active_process = None
                if return_code != 0:
                    raise QualityVoiceRuntimeError(
                        HTTPStatus.SERVICE_UNAVAILABLE,
                        "qwen_quality_voice_generation_failed",
                    )
                if not output_wav.is_file() or output_wav.stat().st_size <= 44:
                    raise QualityVoiceRuntimeError(
                        HTTPStatus.SERVICE_UNAVAILABLE,
                        "qwen_quality_voice_output_missing",
                    )
                with wave.open(str(output_wav), "rb") as audio:
                    valid_wav = (
                        audio.getnchannels() == 1
                        and audio.getsampwidth() == 2
                        and audio.getframerate() == 24000
                        and audio.getnframes() > 0
                    )
                if not valid_wav:
                    raise QualityVoiceRuntimeError(
                        HTTPStatus.SERVICE_UNAVAILABLE,
                        "qwen_quality_voice_output_invalid",
                    )
                return output_wav.read_bytes()
        finally:
            self._generation_lock.release()

    def shutdown(self) -> None:
        with self._process_lock:
            process = self._active_process
        if process is not None:
            terminate_process_group(process)


class QualityVoiceHttpServer(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self, server_address: tuple[str, int], runtime: QualityVoiceRuntime):
        super().__init__(server_address, QualityVoiceRequestHandler)
        self.runtime = runtime


class QualityVoiceRequestHandler(BaseHTTPRequestHandler):
    server: QualityVoiceHttpServer
    server_version = "MindscapeQwenQualityVoice/1.0"

    def log_message(self, format: str, *args: object) -> None:
        print(f"[qwen-quality-voice] {self.address_string()} {format % args}", flush=True)

    def _send_json(self, status: int, payload: dict[str, object]) -> None:
        body = (json.dumps(payload, ensure_ascii=False, sort_keys=True) + "\n").encode(
            "utf-8"
        )
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:
        if self.path != "/health":
            self._send_json(HTTPStatus.NOT_FOUND, {"reason": "not_found"})
            return
        health = self.server.runtime.health()
        status = (
            HTTPStatus.OK
            if health["status"] == "ok"
            else HTTPStatus.SERVICE_UNAVAILABLE
        )
        self._send_json(status, health)

    def do_POST(self) -> None:
        if self.path != "/tts":
            self._send_json(HTTPStatus.NOT_FOUND, {"reason": "not_found"})
            return
        try:
            content_length = int(self.headers.get("Content-Length", "0"))
            if content_length <= 0 or content_length > 8192:
                raise QualityVoiceRequestError(
                    HTTPStatus.REQUEST_ENTITY_TOO_LARGE, "invalid_content_length"
                )
            payload = json.loads(self.rfile.read(content_length).decode("utf-8"))
            text, language_code = parse_synthesis_payload(
                payload, self.server.runtime.config
            )
            audio_bytes = self.server.runtime.synthesize(
                text=text, language_code=language_code
            )
        except json.JSONDecodeError:
            self._send_json(HTTPStatus.BAD_REQUEST, {"reason": "invalid_json_body"})
            return
        except (QualityVoiceRequestError, QualityVoiceRuntimeError) as exc:
            self._send_json(exc.status, {"reason": exc.reason})
            return
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "audio/wav")
        self.send_header("Content-Length", str(len(audio_bytes)))
        self.send_header("X-Mindscape-Voice-Provider", PROVIDER_ID)
        self.send_header("X-Mindscape-Voice-Profile", VOICE_PROFILE_ID)
        self.end_headers()
        try:
            self.wfile.write(audio_bytes)
        except (BrokenPipeError, ConnectionResetError):
            pass


def serve(host: str, port: int, config: RuntimeConfig) -> None:
    runtime = QualityVoiceRuntime(config)
    server = QualityVoiceHttpServer((host, port), runtime)

    def handle_shutdown(_signum: int, _frame: object) -> None:
        runtime.shutdown()
        threading.Thread(target=server.shutdown, daemon=True).start()

    signal.signal(signal.SIGTERM, handle_shutdown)
    signal.signal(signal.SIGINT, handle_shutdown)
    try:
        server.serve_forever(poll_interval=0.25)
    finally:
        runtime.shutdown()
        server.server_close()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8184)
    args = parser.parse_args()
    serve(args.host, args.port, RuntimeConfig.from_env())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
