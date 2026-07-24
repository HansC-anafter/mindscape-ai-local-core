"""Resolve the source Local Core identity without network or DB access."""

import os


def source_runtime_id() -> str:
    return (
        os.getenv("MINDSCAPE_SOURCE_RUNTIME_ID")
        or os.getenv("DEVICE_ID")
        or "local-core-local"
    ).strip()
