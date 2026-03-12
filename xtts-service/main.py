"""
Mindscape XTTS-v2 TTS Service
===============================
FastAPI service wrapping Coqui XTTS-v2 for local speech synthesis.

Endpoints:
  POST /tts           — Synthesize text → audio bytes (mp3/wav)
  POST /tts/clone     — Clone voice from sample + synthesize
  GET  /health        — Health check
  GET  /voices        — List available voice profiles

Speaker voice profiles are loaded from /app/voices/{profile_id}/sample.wav
"""

import logging
import os
import tempfile
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, Response
from pydantic import BaseModel

logger = logging.getLogger("xtts_service")
logging.basicConfig(level=logging.INFO)

app = FastAPI(title="Mindscape XTTS-v2 Service", version="1.0.0")

# ── Globals ──────────────────────────────────────────────────────────────────

_tts = None
_model_loaded = False
VOICES_DIR = Path(os.getenv("XTTS_VOICES_DIR", "/app/voices"))
MODEL_NAME = os.getenv("XTTS_MODEL", "tts_models/multilingual/multi-dataset/xtts_v2")
DEFAULT_LANGUAGE = os.getenv("XTTS_DEFAULT_LANGUAGE", "zh-cn")
USE_GPU = os.getenv("XTTS_USE_GPU", "auto")  # auto | true | false


def _load_model():
    """Lazy-load XTTS-v2 model on first request."""
    global _tts, _model_loaded
    if _model_loaded:
        return _tts

    logger.info("Loading XTTS-v2 model: %s", MODEL_NAME)
    try:
        # PyTorch 2.6+ changed torch.load default to weights_only=True,
        # but Coqui TTS checkpoints contain custom classes (XttsConfig etc.)
        # that require unpickling. Patch torch.load to allow this.
        import torch
        import functools

        _original_torch_load = torch.load

        @functools.wraps(_original_torch_load)
        def _patched_load(*args, **kwargs):
            kwargs.setdefault("weights_only", False)
            return _original_torch_load(*args, **kwargs)

        torch.load = _patched_load

        from TTS.api import TTS

        use_gpu = USE_GPU == "true" or (USE_GPU == "auto" and _has_acceleration())
        logger.info("GPU/MPS acceleration: %s", use_gpu)
        _tts = TTS(MODEL_NAME, gpu=use_gpu)
        _model_loaded = True
        logger.info("XTTS-v2 model loaded successfully")
        return _tts
    except Exception as e:
        logger.error("Failed to load XTTS-v2: %s", e)
        raise RuntimeError(f"XTTS-v2 model load failed: {e}") from e


def _has_acceleration() -> bool:
    """Check if GPU or Apple MPS is available."""
    try:
        import torch

        if torch.backends.mps.is_available():
            return True
        if torch.cuda.is_available():
            return True
    except ImportError:
        pass
    return False


def _get_speaker_wav(voice_profile_id: Optional[str]) -> Optional[str]:
    """Resolve speaker WAV path from voice_profile_id."""
    if not voice_profile_id:
        return None
    profile_dir = VOICES_DIR / voice_profile_id
    for name in ("sample.wav", "reference.wav", "voice.wav"):
        candidate = profile_dir / name
        if candidate.exists():
            return str(candidate)
    logger.warning("No speaker WAV found for profile: %s", voice_profile_id)
    return None


# ── Request/Response Models ───────────────────────────────────────────────────


class TTSRequest(BaseModel):
    text: str
    voice_profile_id: Optional[str] = None
    language: Optional[str] = None
    output_format: str = "wav"  # wav | mp3 (mp3 requires pydub)


class TTSCloneRequest(BaseModel):
    text: str
    speaker_wav_base64: str  # base64-encoded WAV reference audio
    language: Optional[str] = None
    output_format: str = "wav"


# ── Endpoints ─────────────────────────────────────────────────────────────────


@app.get("/health")
async def health():
    return {
        "status": "ok",
        "model": MODEL_NAME,
        "model_loaded": _model_loaded,
        "voices_dir": str(VOICES_DIR),
        "acceleration": _has_acceleration(),
    }


@app.get("/voices")
async def list_voices():
    """List available voice profiles (directories under VOICES_DIR)."""
    if not VOICES_DIR.exists():
        return {"voices": []}
    voices = [
        d.name
        for d in VOICES_DIR.iterdir()
        if d.is_dir() and not d.name.startswith(".")
    ]
    return {"voices": voices}


@app.post("/tts")
async def synthesize(req: TTSRequest):
    """
    Synthesize text to speech using XTTS-v2.

    If voice_profile_id is provided and a sample WAV exists, performs
    zero-shot voice cloning. Otherwise uses a default XTTS-v2 speaker.
    """
    if not req.text.strip():
        raise HTTPException(status_code=400, detail="text cannot be empty")

    try:
        tts = _load_model()
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e))

    language = req.language or DEFAULT_LANGUAGE
    speaker_wav = _get_speaker_wav(req.voice_profile_id)

    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
        out_path = tmp.name

    try:
        logger.info(
            "TTS request: len=%d lang=%s profile=%s",
            len(req.text),
            language,
            req.voice_profile_id,
        )

        if speaker_wav:
            # Zero-shot voice clone with provided speaker
            tts.tts_to_file(
                text=req.text,
                speaker_wav=speaker_wav,
                language=language,
                file_path=out_path,
            )
        else:
            # XTTS-v2 is multi-speaker and always requires a reference wav.
            # Fall back to the 'default' voice profile.
            default_wav = _get_speaker_wav("default")
            if not default_wav:
                raise HTTPException(
                    status_code=400,
                    detail="No voice_profile_id provided and no default voice profile found. "
                    "Place a sample.wav in data/tts/voices/default/",
                )
            tts.tts_to_file(
                text=req.text,
                speaker_wav=default_wav,
                language=language,
                file_path=out_path,
            )

        # Convert to mp3 if requested
        if req.output_format == "mp3":
            mp3_path = out_path.replace(".wav", ".mp3")
            try:
                from pydub import AudioSegment

                AudioSegment.from_wav(out_path).export(mp3_path, format="mp3")
                out_path = mp3_path
                media_type = "audio/mpeg"
            except ImportError:
                logger.warning("pydub not installed, returning wav instead of mp3")
                media_type = "audio/wav"
        else:
            media_type = "audio/wav"

        with open(out_path, "rb") as f:
            audio_bytes = f.read()

        logger.info(
            "TTS done: %d bytes, format=%s", len(audio_bytes), req.output_format
        )
        return Response(content=audio_bytes, media_type=media_type)

    finally:
        for p in [out_path, out_path.replace(".wav", ".mp3")]:
            try:
                Path(p).unlink(missing_ok=True)
            except Exception:
                pass


@app.post("/tts/clone")
async def synthesize_clone(req: TTSCloneRequest):
    """
    Zero-shot voice clone: provide reference WAV as base64, get audio back.
    """
    import base64

    try:
        wav_bytes = base64.b64decode(req.speaker_wav_base64)
    except Exception:
        raise HTTPException(
            status_code=400, detail="Invalid base64 in speaker_wav_base64"
        )

    try:
        tts = _load_model()
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e))

    language = req.language or DEFAULT_LANGUAGE

    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as ref_tmp:
        ref_tmp.write(wav_bytes)
        ref_path = ref_tmp.name

    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as out_tmp:
        out_path = out_tmp.name

    try:
        tts.tts_to_file(
            text=req.text,
            speaker_wav=ref_path,
            language=language,
            file_path=out_path,
        )
        with open(out_path, "rb") as f:
            audio_bytes = f.read()
        return Response(content=audio_bytes, media_type="audio/wav")
    finally:
        for p in [ref_path, out_path]:
            try:
                Path(p).unlink(missing_ok=True)
            except Exception:
                pass
