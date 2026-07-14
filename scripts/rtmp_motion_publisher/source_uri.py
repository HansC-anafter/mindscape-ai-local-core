from __future__ import annotations

from urllib.parse import urlsplit, urlunsplit


NETWORK_SCHEMES = {"http", "https", "rtmp", "rtmps", "rtsp", "rtsps"}


def capture_input_kind(source_kind: str, transport_kind: str) -> str:
    normalized_source = str(source_kind or "").strip()
    normalized_transport = str(transport_kind or "").strip()
    if normalized_source == "external_provider_camera":
        return "external_provider_adapter"
    if normalized_transport == "rtsps":
        return "remote_webrtc"
    if "rtmp" in normalized_transport:
        return "rtmp_adapter"
    return "live_media"


def public_input_uri(value: str) -> str:
    """Remove credentials and query material from persisted source evidence."""

    source = str(value or "").strip()
    scheme = source.partition(":")[0].lower()
    if scheme not in NETWORK_SCHEMES:
        return source
    try:
        parsed = urlsplit(source)
        hostname = parsed.hostname or "redacted-host"
        if ":" in hostname and not hostname.startswith("["):
            hostname = f"[{hostname}]"
        netloc = f"{hostname}:{parsed.port}" if parsed.port else hostname
        return urlunsplit((parsed.scheme.lower(), netloc, parsed.path, "", ""))
    except ValueError:
        return f"{scheme}://redacted-host"


__all__ = ["capture_input_kind", "public_input_uri"]
