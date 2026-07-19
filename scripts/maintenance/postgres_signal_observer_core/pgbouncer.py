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


def validate_pgbouncer_correlation(
    payload: Any,
    *,
    target_postgres_pid: int,
) -> dict[str, Any]:
    """Return the exact payload-free correlation schema or fail closed."""

    if type(payload) is not dict or set(payload) != {
        "status",
        "application_name",
        "database",
        "user_sha256",
        "client_address_class",
        "client_remote_pid",
        "postgres_remote_pid",
    }:
        raise RuntimeError("pgbouncer_correlation_projection_invalid")
    database = payload.get("database")
    user_sha256 = payload.get("user_sha256")
    address_class = payload.get("client_address_class")
    client_remote_pid = payload.get("client_remote_pid")
    postgres_remote_pid = payload.get("postgres_remote_pid")
    if (
        payload.get("status") != "correlated"
        or type(database) is not str
        or re.fullmatch(r"[A-Za-z0-9_][A-Za-z0-9_.-]{0,62}", database) is None
        or type(user_sha256) is not str
        or re.fullmatch(r"[0-9a-f]{64}", user_sha256) is None
        or type(address_class) is not str
        or address_class
        not in {"local", "loopback", "private", "public", "unknown"}
        or type(client_remote_pid) is not int
        or not 0 < client_remote_pid <= 4_194_304
        or type(postgres_remote_pid) is not int
        or postgres_remote_pid != target_postgres_pid
    ):
        raise RuntimeError("pgbouncer_correlation_projection_invalid")
    return {
        "status": "correlated",
        "application_name": _application_name(payload.get("application_name")),
        "database": database,
        "user_sha256": user_sha256,
        "client_address_class": address_class,
        "client_remote_pid": client_remote_pid,
        "postgres_remote_pid": postgres_remote_pid,
    }


class PgBouncerCorrelationClient:
    """Read SHOW metadata once; never query PostgreSQL or retain credentials."""

    def __init__(
        self,
        admin_url: str,
        *,
        connect_timeout_seconds: int = 2,
        expected_application_name: str | None = None,
    ) -> None:
        self.admin_url = str(admin_url).strip()
        self.connect_timeout_seconds = max(1, min(int(connect_timeout_seconds), 5))
        self.expected_application_name = (
            _application_name(expected_application_name)
            if expected_application_name is not None
            else None
        )

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
        raw_application_name = str(client.get("application_name") or "").strip()
        application_name = (
            self.expected_application_name
            if not raw_application_name and self.expected_application_name
            else _application_name(raw_application_name)
        )
        if (
            self.expected_application_name is not None
            and application_name != self.expected_application_name
        ):
            raise RuntimeError("pgbouncer_application_name_mismatch")
        client_remote_pid = int(client.get("remote_pid") or 0)
        postgres_remote_pid = int(server.get("remote_pid") or 0)
        if client_remote_pid <= 0 or postgres_remote_pid != int(target_postgres_pid):
            raise RuntimeError("pgbouncer_pid_correlation_invalid")
        return validate_pgbouncer_correlation(
            {
                "status": "correlated",
                "application_name": application_name,
                "database": str(
                    client.get("database") or server.get("database") or ""
                ),
                "user_sha256": _stable_hash(
                    client.get("user") or server.get("user")
                ),
                "client_address_class": _address_class(client.get("addr")),
                "client_remote_pid": client_remote_pid,
                "postgres_remote_pid": postgres_remote_pid,
            },
            target_postgres_pid=target_postgres_pid,
        )
