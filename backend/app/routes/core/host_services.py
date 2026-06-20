"""Host sidecar service proxy routes."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from fastapi.responses import Response

from backend.app.services.host_services.xtts_proxy import (
    XTTSSynthesisRequest,
    XTTSSynthesisUnavailable,
    synthesize_xtts_audio,
)
from backend.app.services.host_services.whisper_proxy import (
    WhisperTranscriptionInvalidRequest,
    WhisperTranscriptionRequest,
    WhisperTranscriptionUnavailable,
    transcribe_whisper_audio,
)
from backend.app.services.host_services.capture_relay_proxy import (
    CaptureRelayRequest,
    CaptureRelayUnavailable,
    call_capture_relay_control,
)


router = APIRouter(prefix="/api/v1/host/services", tags=["host-services"])


@router.post("/xtts/tts")
async def post_xtts_tts(payload: XTTSSynthesisRequest) -> Response:
    try:
        result = await synthesize_xtts_audio(payload)
    except XTTSSynthesisUnavailable as exc:
        raise HTTPException(status_code=503, detail=exc.to_detail()) from exc
    return Response(content=result.audio_bytes, media_type=result.media_type)


@router.post("/stt/transcribe")
async def post_stt_transcribe(payload: WhisperTranscriptionRequest):
    try:
        result = await transcribe_whisper_audio(payload)
    except WhisperTranscriptionInvalidRequest as exc:
        raise HTTPException(status_code=422, detail=exc.to_detail()) from exc
    except WhisperTranscriptionUnavailable as exc:
        raise HTTPException(status_code=503, detail=exc.to_detail()) from exc
    return {
        "text": result.text,
        "segments": result.segments,
        "language": result.language,
        "duration": result.duration,
    }


@router.get("/capture-relay/status")
async def get_capture_relay_status(stream_name: str = "external-camera"):
    try:
        return await call_capture_relay_control(
            CaptureRelayRequest(action="status", stream_name=stream_name)
        )
    except CaptureRelayUnavailable as exc:
        raise HTTPException(status_code=503, detail=exc.to_detail()) from exc


@router.post("/capture-relay")
async def post_capture_relay(payload: CaptureRelayRequest):
    try:
        return await call_capture_relay_control(payload)
    except CaptureRelayUnavailable as exc:
        raise HTTPException(status_code=503, detail=exc.to_detail()) from exc


__all__ = ["router"]
