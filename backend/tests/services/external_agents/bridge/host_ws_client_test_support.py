import base64
import json


def _fake_jwt(payload: dict) -> str:
    encoded = base64.urlsafe_b64encode(
        json.dumps(payload, separators=(",", ":"), ensure_ascii=True).encode("utf-8")
    ).decode("utf-8").rstrip("=")
    return f"header.{encoded}.signature"
