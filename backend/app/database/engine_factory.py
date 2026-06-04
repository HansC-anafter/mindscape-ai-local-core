"""SQLAlchemy engine helpers for PgBouncer transaction-mode operation."""

from __future__ import annotations

import os
from typing import Any

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.pool import NullPool

from app.database.config import get_engine_kwargs


def _application_name(application_name: str | None) -> str:
    return (
        str(application_name or "").strip()
        or os.getenv("DB_APPLICATION_NAME", "").strip()
    )


def _with_connect_args(
    kwargs: dict[str, Any],
    connect_args: dict[str, Any] | None,
) -> dict[str, Any]:
    if not connect_args:
        return kwargs
    merged = dict(kwargs.get("connect_args") or {})
    merged.update(connect_args)
    kwargs["connect_args"] = merged
    return kwargs


def _with_application_name(
    kwargs: dict[str, Any], application_name: str | None
) -> dict[str, Any]:
    name = _application_name(application_name)
    if not name:
        return kwargs
    connect_args = dict(kwargs.get("connect_args") or {})
    connect_args["application_name"] = name
    kwargs["connect_args"] = connect_args
    return kwargs


def create_transaction_engine(
    url: str,
    application_name: str | None = None,
    connect_args: dict[str, Any] | None = None,
    engine_options: dict[str, Any] | None = None,
) -> Engine:
    """Create a bounded QueuePool engine for normal transaction-pool traffic."""

    kwargs = _with_connect_args(get_engine_kwargs(), connect_args)
    kwargs = _with_application_name(kwargs, application_name)
    kwargs.update(engine_options or {})
    return create_engine(url, **kwargs)


def create_readonly_transaction_engine(
    url: str,
    application_name: str | None = None,
    connect_args: dict[str, Any] | None = None,
    engine_options: dict[str, Any] | None = None,
) -> Engine:
    """Create a bounded QueuePool engine for explicit read-only replica traffic."""

    return create_transaction_engine(
        url,
        application_name=application_name,
        connect_args=connect_args,
        engine_options=engine_options,
    )


def create_transient_transaction_engine(
    url: str,
    application_name: str | None = None,
    connect_args: dict[str, Any] | None = None,
    engine_options: dict[str, Any] | None = None,
) -> Engine:
    """Create a one-shot transaction-pool engine that keeps no client pool."""

    kwargs = _with_connect_args(
        {
            "echo": os.getenv("SQLALCHEMY_ECHO", "false").lower() == "true",
            "poolclass": NullPool,
            "pool_pre_ping": True,
        },
        connect_args,
    )
    kwargs = _with_application_name(
        kwargs,
        application_name,
    )
    kwargs.update(engine_options or {})
    return create_engine(url, **kwargs)


def create_session_semantics_engine(
    url: str,
    application_name: str | None = None,
    connect_args: dict[str, Any] | None = None,
    engine_options: dict[str, Any] | None = None,
) -> Engine:
    """Create a direct/session-semantics engine for DDL, migrations, and locks."""

    kwargs = _with_connect_args(
        {
            "echo": os.getenv("SQLALCHEMY_ECHO", "false").lower() == "true",
            "poolclass": NullPool,
            "pool_pre_ping": True,
        },
        connect_args,
    )
    kwargs = _with_application_name(
        kwargs,
        application_name,
    )
    kwargs.update(engine_options or {})
    return create_engine(url, **kwargs)
