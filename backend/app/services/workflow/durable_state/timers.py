"""Durable timer payload validation without a new scheduler."""

from datetime import datetime


def validate_timer(payload: dict) -> None:
    if not payload.get("timer_id") or not payload.get("deadline"):
        raise ValueError("timer_id and deadline are required")
    datetime.fromisoformat(payload["deadline"].replace("Z", "+00:00"))
