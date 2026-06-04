"""Host sidecar service proxy routes."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from fastapi.responses import Response

from backend.app.services.host_services.xtts_proxy import (
    XTTSSynthesisRequest,
    XTTSSynthesisUnavailable,
    synthesize_xtts_audio,
)


router = APIRouter(prefix="/api/v1/host/services", tags=["host-services"])


@router.post("/xtts/tts")
async def post_xtts_tts(payload: XTTSSynthesisRequest) -> Response:
    try:
        result = await synthesize_xtts_audio(payload)
    except XTTSSynthesisUnavailable as exc:
        raise HTTPException(status_code=503, detail=exc.to_detail()) from exc
    return Response(content=result.audio_bytes, media_type=result.media_type)


__all__ = ["router"]
