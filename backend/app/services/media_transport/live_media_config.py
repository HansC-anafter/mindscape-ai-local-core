"""Fail-closed runtime configuration for the public live media relay."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse


DEFAULT_MEDIA_SESSION_TTL_SECONDS = 4 * 60 * 60
MAX_MEDIA_SESSION_TTL_SECONDS = 4 * 60 * 60


class LiveMediaConfigError(RuntimeError):
    """Raised when the formal relay configuration is incomplete or unsafe."""


def _required_env(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise LiveMediaConfigError(f"{name.lower()}_required")
    return value


def _validated_origin(name: str, value: str, schemes: set[str]) -> str:
    parsed = urlparse(value)
    if parsed.scheme not in schemes or not parsed.hostname:
        raise LiveMediaConfigError(f"{name.lower()}_invalid")
    if parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise LiveMediaConfigError(f"{name.lower()}_must_not_contain_credentials")
    return value.rstrip("/")


@dataclass(frozen=True)
class LiveMediaConfig:
    public_webrtc_origin: str
    public_rtmps_origin: str
    receiver_rtsps_origin: str
    jwt_private_key_path: Path
    jwt_key_id: str
    jwt_issuer: str
    jwt_audience: str
    session_ttl_seconds: int = DEFAULT_MEDIA_SESSION_TTL_SECONDS

    @classmethod
    def from_env(cls) -> "LiveMediaConfig":
        ttl = int(
            os.getenv(
                "LOCAL_CORE_LIVE_MEDIA_SESSION_TTL_SECONDS",
                str(DEFAULT_MEDIA_SESSION_TTL_SECONDS),
            )
        )
        if ttl < 60 or ttl > MAX_MEDIA_SESSION_TTL_SECONDS:
            raise LiveMediaConfigError("live_media_session_ttl_out_of_range")
        key_id = _required_env("LOCAL_CORE_LIVE_MEDIA_JWT_KEY_ID")
        if not key_id.replace("-", "").replace("_", "").isalnum():
            raise LiveMediaConfigError("local_core_live_media_jwt_key_id_invalid")
        return cls(
            public_webrtc_origin=_validated_origin(
                "LOCAL_CORE_LIVE_MEDIA_WEBRTC_ORIGIN",
                _required_env("LOCAL_CORE_LIVE_MEDIA_WEBRTC_ORIGIN"),
                {"https"},
            ),
            public_rtmps_origin=_validated_origin(
                "LOCAL_CORE_LIVE_MEDIA_RTMPS_ORIGIN",
                _required_env("LOCAL_CORE_LIVE_MEDIA_RTMPS_ORIGIN"),
                {"rtmps"},
            ),
            receiver_rtsps_origin=_validated_origin(
                "LOCAL_CORE_LIVE_MEDIA_RTSPS_ORIGIN",
                _required_env("LOCAL_CORE_LIVE_MEDIA_RTSPS_ORIGIN"),
                {"rtsps"},
            ),
            jwt_private_key_path=Path(
                _required_env("LOCAL_CORE_LIVE_MEDIA_JWT_PRIVATE_KEY_PATH")
            ).expanduser(),
            jwt_key_id=key_id,
            jwt_issuer=_required_env("LOCAL_CORE_LIVE_MEDIA_JWT_ISSUER"),
            jwt_audience=_required_env("LOCAL_CORE_LIVE_MEDIA_JWT_AUDIENCE"),
            session_ttl_seconds=ttl,
        )


__all__ = [
    "DEFAULT_MEDIA_SESSION_TTL_SECONDS",
    "LiveMediaConfig",
    "LiveMediaConfigError",
    "MAX_MEDIA_SESSION_TTL_SECONDS",
]
