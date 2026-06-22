"""Error helpers for durable capability install jobs."""

from __future__ import annotations

import json


def install_job_exception_message(exc: Exception) -> str:
    """Return a durable, non-empty error message for install job failures."""

    detail = getattr(exc, "detail", None)
    if detail is not None:
        if isinstance(detail, str):
            return detail or exc.__class__.__name__
        try:
            return json.dumps(detail, ensure_ascii=False, sort_keys=True, default=str)
        except Exception:
            return str(detail) or exc.__class__.__name__

    message = str(exc).strip()
    return message or exc.__class__.__name__
