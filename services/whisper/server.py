"""
Whisper ASR Service — FastAPI wrapper for faster-whisper.

Exposes POST /transcribe and GET /health.
Matches the API contract expected by whisper_runtime._transcribe_local.
"""

import base64
import io
import time
import logging
import tempfile
import os

from fastapi import FastAPI
from pydantic import BaseModel
from typing import Optional, List, Dict, Any

app = FastAPI(title="Whisper ASR Service", version="1.0.0")
logger = logging.getLogger("whisper-service")
logging.basicConfig(level=logging.INFO)

# Lazy init
_model = None
_model_size = None


def get_model(model_name: str = "medium", device: str = "cpu"):
    """Lazy-load faster-whisper model."""
    global _model, _model_size
    # Normalise: "openai/whisper-medium" -> "medium"
    size = model_name.split("-")[-1] if "/" in model_name else model_name
    if size not in ("tiny", "base", "small", "medium", "large-v2", "large-v3"):
        size = "small"
    if _model is not None and _model_size == size:
        return _model
    logger.info(f"Loading faster-whisper model: {size} (device={device})")
    from faster_whisper import WhisperModel

    compute = "int8" if device == "cpu" else "float16"
    _model = WhisperModel(size, device=device, compute_type=compute)
    _model_size = size
    logger.info(f"Model loaded: {size}")
    return _model


class TranscribeRequest(BaseModel):
    audio: str  # base64-encoded audio bytes
    language: Optional[str] = "auto"
    task: str = "transcribe"
    model: str = "openai/whisper-medium"
    device: str = "cpu"


class Segment(BaseModel):
    start: float
    end: float
    text: str


class TranscribeResponse(BaseModel):
    text: str
    segments: List[Dict[str, Any]]
    language: str
    duration: float


@app.get("/health")
async def health():
    return {"status": "healthy", "model_loaded": _model is not None}


@app.post("/transcribe", response_model=TranscribeResponse)
async def transcribe(req: TranscribeRequest):
    t0 = time.time()

    # Decode audio
    audio_bytes = base64.b64decode(req.audio)
    logger.info(
        f"Received audio: {len(audio_bytes)} bytes, lang={req.language}, model={req.model}"
    )

    # Write to tmp file (faster-whisper reads files)
    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
        tmp.write(audio_bytes)
        tmp_path = tmp.name

    try:
        model = get_model(req.model, req.device)
        lang = None if req.language == "auto" else req.language

        segments_iter, info = model.transcribe(
            tmp_path,
            language=lang,
            task=req.task,
            beam_size=5,
            vad_filter=True,
        )

        segments = []
        full_text_parts = []
        for seg in segments_iter:
            segments.append(
                {
                    "start": round(seg.start, 3),
                    "end": round(seg.end, 3),
                    "text": seg.text.strip(),
                }
            )
            full_text_parts.append(seg.text.strip())

        full_text = " ".join(full_text_parts)
        elapsed = time.time() - t0
        logger.info(
            f"Transcription done: {len(segments)} segs, "
            f"lang={info.language}, dur={info.duration:.1f}s, elapsed={elapsed:.1f}s"
        )

        return TranscribeResponse(
            text=full_text,
            segments=segments,
            language=info.language,
            duration=info.duration,
        )
    finally:
        os.unlink(tmp_path)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8006)
