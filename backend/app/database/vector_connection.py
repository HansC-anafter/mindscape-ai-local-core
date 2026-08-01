"""Canonical DBAPI acquisition for vector runtime callers."""

from __future__ import annotations

import os
from collections.abc import Mapping
from typing import Any

from backend.app.database.application_identity import application_name_for_role
from backend.app.database.connection_factory import ConnectionFactory


def get_vector_dbapi_connection(
    postgres_config: Mapping[str, Any] | None = None,
):
    """Return the bounded default vector connection or one explicit custom client."""
    if not postgres_config:
        return ConnectionFactory().get_raw_connection(role="vector")

    try:
        import psycopg2
    except ImportError as exc:  # pragma: no cover - runtime dependency gate
        raise RuntimeError("psycopg2_not_installed") from exc

    connect_args = {
        key: value for key, value in dict(postgres_config).items() if value is not None
    }
    connect_args["application_name"] = application_name_for_role("vector")
    connect_args.setdefault(
        "connect_timeout",
        int(os.getenv("VECTOR_DB_CONNECT_TIMEOUT", "5")),
    )
    return psycopg2.connect(**connect_args)


__all__ = ["get_vector_dbapi_connection"]
