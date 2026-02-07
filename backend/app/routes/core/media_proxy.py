import httpx
from fastapi import APIRouter, HTTPException, Query, Response
from fastapi.responses import StreamingResponse
import logging

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/media", tags=["media"])

ALLOWED_HOSTS = {
    "scontent.cdninstagram.com",
    "scontent-tpe1-1.cdninstagram.com",
    "scontent-hkg4-1.cdninstagram.com",
    "scontent.fkhh1-2.fna.fbcdn.net",
    "instagram.com",
    "cdninstagram.com",
    "fbcdn.net",
}


@router.get("/image")
async def proxy_image(url: str = Query(..., description="URL of the image to proxy")):
    """
    Proxy an image from an external source (e.g. Instagram) to avoid CORS issues.
    """
    try:
        from urllib.parse import urlparse

        parsed = urlparse(url)
        hostname = (parsed.hostname or "").lower()

        # Basic allowlist check via suffix
        allowed = False
        for allowed_host in ALLOWED_HOSTS:
            if hostname == allowed_host or hostname.endswith("." + allowed_host):
                allowed = True
                break

        if not allowed:
            # Fallback: strict check failed, verify if it looks like an Instagram URL pattern
            if "instagram" in hostname or "fbcdn" in hostname:
                allowed = True

        if not allowed:
            raise HTTPException(status_code=403, detail="Host not allowed")

        async def iter_content():
            async with httpx.AsyncClient() as client:
                try:
                    async with client.stream(
                        "GET", url, follow_redirects=True, timeout=10.0
                    ) as response:
                        if response.status_code != 200:
                            raise HTTPException(
                                status_code=response.status_code,
                                detail="Failed to fetch image",
                            )

                        # Forward relevant headers
                        content_type = response.headers.get(
                            "content-type", "image/jpeg"
                        )

                        # Yield the content
                        async for chunk in response.aiter_bytes():
                            yield chunk
                except Exception as e:
                    logger.error(f"Error proxying image {url}: {e}")
                    raise HTTPException(
                        status_code=500, detail="Failed to fetch image stream"
                    )

        # We need to fetch headers first to set Content-Type correctly,
        # but StreamingResponse with a generator is tricky for headers.
        # Simpler approach for small images (avatars): fetch content then return Response.
        # But for correctness with Async, let's just fetch it.

        async with httpx.AsyncClient() as client:
            resp = await client.get(url, follow_redirects=True, timeout=10.0)
            if resp.status_code != 200:
                return Response(status_code=resp.status_code)

            return Response(
                content=resp.content,
                media_type=resp.headers.get("content-type", "image/jpeg"),
                headers={
                    "Cache-Control": "public, max-age=86400",
                    "Access-Control-Allow-Origin": "*",
                },
            )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Proxy error: {e}")
        raise HTTPException(status_code=500, detail=str(e))
