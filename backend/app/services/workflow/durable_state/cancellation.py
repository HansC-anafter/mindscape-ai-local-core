"""Cancellation request validation without a cancellation queue."""


def validate_cancellation(payload: dict) -> None:
    if not payload.get("reason"):
        raise ValueError("cancellation reason is required")
