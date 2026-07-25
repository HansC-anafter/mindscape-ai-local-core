"""External message payload validation without an inbox service."""


def validate_external_message(payload: dict) -> None:
    if not payload.get("external_message_id"):
        raise ValueError("external_message_id is required")
