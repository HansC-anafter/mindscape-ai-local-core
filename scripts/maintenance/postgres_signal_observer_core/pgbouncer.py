"""One-shot PgBouncer metadata correlation for a signal target."""

from __future__ import annotations

import hashlib
import ipaddress
import re
from typing import Any

import psycopg2


def _rows(cursor: Any) -> list[dict[str, Any]]:
    columns = [str(item.name) for item in cursor.description]
    return [dict(zip(columns, row)) for row in cursor.fetchall()]


def _address_class(value: Any) -> str:
    candidate = str(value or "").strip()
    if not candidate or candidate.lower() in {"unix", "local"}:
        return "local"
    try:
        address = ipaddress.ip_address(candidate)
    except ValueError:
        return "unknown"
    if address.is_loopback:
        return "loopback"
    if address.is_private:
        return "private"
    return "public"


def _stable_hash(value: Any) -> str:
    return hashlib.sha256(str(value or "").encode("utf-8")).hexdigest()


def _application_name(value: Any) -> str:
    candidate = str(value or "").strip()
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,62}", candidate):
        raise RuntimeError("pgbouncer_application_name_invalid")
    return candidate


class PgBouncerCorrelationClient:
    """Read SHOW metadata once; never query PostgreSQL or retain credentials."""

    def __init__(self, admin_url: str, *, connect_timeout_seconds: int = 2) -> None:
        self.admin_url = str(admin_url).strip()
        self.connect_timeout_seconds = max(1, min(int(connect_timeout_seconds), 5))

    def correlate(self, target_postgres_pid: int) -> dict[str, Any]:
        if not self.admin_url:
            raise RuntimeError("pgbouncer_admin_url_missing")
        connection = psycopg2.connect(
            self.admin_url,
            connect_timeout=self.connect_timeout_seconds,
            application_name="postgres-signal-observer",
        )
        try:
            connection.autocommit = True
            with connection.cursor() as cursor:
                cursor.execute("SHOW SERVERS")
                servers = _rows(cursor)
                cursor.execute("SHOW CLIENTS")
                clients = _rows(cursor)
        finally:
            connection.close()

        server = next(
            (
                row
                for row in servers
                if str(row.get("remote_pid") or "") == str(int(target_postgres_pid))
            ),
            None,
        )
        if server is None:
            raise RuntimeError("pgbouncer_target_server_link_unavailable")
        server_ptr = str(server.get("ptr") or "")
        server_link = str(server.get("link") or "")
        client = next(
            (
                row
                for row in clients
                if str(row.get("ptr") or "") == server_link
                or str(row.get("link") or "") == server_ptr
            ),
            None,
        )
        if client is None:
            raise RuntimeError("pgbouncer_target_client_link_unavailable")
        application_name = _application_name(client.get("application_name"))
        client_remote_pid = int(client.get("remote_pid") or 0)
        postgres_remote_pid = int(server.get("remote_pid") or 0)
        if client_remote_pid <= 0 or postgres_remote_pid != int(target_postgres_pid):
            raise RuntimeError("pgbouncer_pid_correlation_invalid")
        return {
            "status": "correlated",
            "application_name": application_name,
            "database": str(client.get("database") or server.get("database") or ""),
            "user_sha256": _stable_hash(client.get("user") or server.get("user")),
            "client_address_class": _address_class(client.get("addr")),
            "client_remote_pid": client_remote_pid,
            "postgres_remote_pid": postgres_remote_pid,
        }
