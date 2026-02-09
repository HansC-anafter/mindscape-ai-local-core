import logging
from typing import Optional
from urllib.parse import urlparse

import httpx
from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import StreamingResponse
from fastapi.middleware.cors import CORSMiddleware

# Configure logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger("media-proxy")

app = FastAPI(
    title="Mindscape Media Proxy",
    description="Dedicated microservice for proxying remote media to avoid CORS issues and isolate I/O load.",
    version="1.0.0",
)

# CORS middleware
# Allow all origins since this is a local tool and images need to be embedded in various contexts
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["GET", "OPTIONS", "HEAD"],
    allow_headers=["*"],
)


def _is_allowed_media_url(url: str) -> bool:
    try:
        parsed = urlparse(url)
        if parsed.scheme not in ("http", "https"):
            return False
        host = (parsed.hostname or "").lower()
        if not host:
            return False

        # Allow localhost/127.0.0.1 for testing
        if host in ("localhost", "127.0.0.1"):
            return True

        # Instagram CDN commonly uses fbcdn.net subdomains.
        if host.endswith(".fbcdn.net"):
            return True

        # Some Instagram media uses cdninstagram.com subdomains
        if host == "cdninstagram.com" or host.endswith(".cdninstagram.com"):
            return True

        # Allow main instagram domain
        if host == "instagram.com" or host.endswith(".instagram.com"):
            return True

        # Add other safe CDNs here as needed

        # Deny by default for security
        return False
    except Exception:
        return False


@app.get("/health")
async def health_check():
    return {"status": "ok", "service": "media-proxy"}


@app.get("/api/v1/media/image")
async def proxy_image(
    url: str = Query(..., description="Remote image URL to proxy"),
    timeout_seconds: float = Query(10.0, ge=1.0, le=30.0),
):
    """
    Proxy an image from a remote URL.
    Streams the response to minimize memory usage.
    """
    if not _is_allowed_media_url(url):
        raise HTTPException(status_code=400, detail="Unsupported media URL host")

    # Create client WITHOUT context manager - we must keep it alive during streaming
    client = httpx.AsyncClient(
        timeout=httpx.Timeout(timeout_seconds),
        follow_redirects=True,
        headers={
            "User-Agent": "MindscapeMediaProxy/1.0",
            "Accept": "image/*,*/*;q=0.8",
            "Referer": "https://www.instagram.com/",
            "Origin": "https://www.instagram.com",
        },
    )

    try:
        req = client.build_request("GET", url)
        resp = await client.send(req, stream=True)

        if resp.status_code >= 400:
            await resp.aclose()
            await client.aclose()
            raise HTTPException(
                status_code=resp.status_code, detail="Upstream image fetch failed"
            )

        content_type: Optional[str] = resp.headers.get("content-type")
        if not content_type or not content_type.lower().startswith("image/"):
            await resp.aclose()
            await client.aclose()
            raise HTTPException(
                status_code=400,
                detail=f"Invalid content type: {content_type}. Only images are supported.",
            )

        # Forward appropriate headers
        response_headers = {
            "Content-Type": content_type or "application/octet-stream",
            "Cache-Control": "public, max-age=3600",
            "Cross-Origin-Resource-Policy": "cross-origin",
            "Access-Control-Allow-Origin": "*",
            "X-Content-Type-Options": "nosniff",
        }

        # Stream content - client/response cleanup happens in the generator
        async def iterate_stream():
            try:
                async for chunk in resp.aiter_bytes():
                    yield chunk
            finally:
                # Ensure cleanup happens even if client disconnects mid-stream
                await resp.aclose()
                await client.aclose()

        return StreamingResponse(
            iterate_stream(),
            headers=response_headers,
            media_type=content_type,
            status_code=resp.status_code,
        )

    except HTTPException:
        raise
    except Exception as e:
        # Cleanup on error
        try:
            await client.aclose()
        except Exception:
            pass
        logger.error(f"proxy_image failed for {url}: {e}")
        raise HTTPException(status_code=500, detail="Failed to proxy image")
