"""Source-owned isolated PgBouncer admin environment for the observer drill."""

from __future__ import annotations

import hashlib
import json
import os
import stat
from pathlib import Path
from types import MappingProxyType
from typing import Any, Mapping
from urllib.parse import quote, unquote, urlsplit

from .drill_bootstrap import DisposableDrillBootstrapConfig
from .drill_escalation import (
    POSTGRES_BOOTSTRAP_ENVIRONMENT_KEYS,
    load_postgres_bootstrap_environment,
    serialize_postgres_bootstrap_environment,
)


PGBOUNCER_ADMIN_ENVIRONMENT_KEY = "PGBOUNCER_ADMIN_URL"
PGBOUNCER_ADMIN_DATABASE = "pgbouncer"
PGBOUNCER_ADMIN_LOOPBACK_HOST = "127.0.0.1"
PGBOUNCER_ADMIN_PORT = 6432
MAX_PGBOUNCER_PRECONDITION_BYTES = 65_536


def serialize_disposable_pgbouncer_config(
    assignments: Mapping[str, str],
) -> bytes:
    """Produce the exact isolated PgBouncer config from validated credentials."""

    serialize_postgres_bootstrap_environment(assignments)
    database = assignments["POSTGRES_DB"]
    username = assignments["POSTGRES_USER"]
    password = assignments["POSTGRES_PASSWORD"]
    return (
        "[databases]\n"
        f"{database} = host=runtime-db-observer-drill-postgres "
        f"port=5432 dbname={database} user={username} "
        f"password={password}\n\n"
        "[pgbouncer]\n"
        "listen_addr = 0.0.0.0\n"
        f"listen_port = {PGBOUNCER_ADMIN_PORT}\n"
        "auth_type = plain\n"
        "auth_file = /etc/pgbouncer/userlist.txt\n"
        "pool_mode = session\n"
        "max_client_conn = 8\n"
        "default_pool_size = 2\n"
        "min_pool_size = 0\n"
        "reserve_pool_size = 0\n"
        "server_reset_query = DISCARD ALL\n"
        "ignore_startup_parameters = extra_float_digits\n"
    ).encode("utf-8")


def serialize_disposable_pgbouncer_userlist(
    assignments: Mapping[str, str],
) -> bytes:
    """Produce the exact isolated PgBouncer userlist from validated credentials."""

    serialize_postgres_bootstrap_environment(assignments)
    return (
        f'"{assignments["POSTGRES_USER"]}" '
        f'"{assignments["POSTGRES_PASSWORD"]}"\n'
    ).encode("utf-8")


def _load_exact_0600_precondition(path: Path, *, failure: str) -> bytes:
    candidate = Path(path)
    nofollow = getattr(os, "O_NOFOLLOW", None)
    if not isinstance(nofollow, int):
        raise RuntimeError(f"{failure}_nofollow_unavailable")
    flags = os.O_RDONLY | nofollow
    cloexec = getattr(os, "O_CLOEXEC", None)
    if isinstance(cloexec, int):
        flags |= cloexec
    try:
        descriptor = os.open(candidate, flags)
    except OSError as exc:
        raise RuntimeError(f"{failure}_unavailable") from exc
    try:
        metadata = os.fstat(descriptor)
        if (
            not stat.S_ISREG(metadata.st_mode)
            or stat.S_IMODE(metadata.st_mode) != 0o600
            or metadata.st_size > MAX_PGBOUNCER_PRECONDITION_BYTES
        ):
            raise RuntimeError(f"{failure}_contract_invalid")
        chunks: list[bytes] = []
        remaining = MAX_PGBOUNCER_PRECONDITION_BYTES + 1
        while remaining > 0:
            chunk = os.read(descriptor, remaining)
            if not chunk:
                break
            chunks.append(chunk)
            remaining -= len(chunk)
        content = b"".join(chunks)
        if len(content) > MAX_PGBOUNCER_PRECONDITION_BYTES:
            raise RuntimeError(f"{failure}_contract_invalid")
        return content
    except OSError as exc:
        raise RuntimeError(f"{failure}_unavailable") from exc
    finally:
        os.close(descriptor)


def _admin_url(assignments: Mapping[str, str]) -> str:
    username = quote(assignments["POSTGRES_USER"], safe="")
    password = quote(assignments["POSTGRES_PASSWORD"], safe="")
    value = (
        f"postgresql://{username}:{password}@{PGBOUNCER_ADMIN_LOOPBACK_HOST}:"
        f"{PGBOUNCER_ADMIN_PORT}/{PGBOUNCER_ADMIN_DATABASE}"
    )
    parsed = urlsplit(value)
    if (
        parsed.scheme != "postgresql"
        or parsed.hostname != PGBOUNCER_ADMIN_LOOPBACK_HOST
        or parsed.port != PGBOUNCER_ADMIN_PORT
        or parsed.path != f"/{PGBOUNCER_ADMIN_DATABASE}"
        or parsed.query
        or parsed.fragment
        or unquote(parsed.username or "") != assignments["POSTGRES_USER"]
        or unquote(parsed.password or "") != assignments["POSTGRES_PASSWORD"]
    ):
        raise RuntimeError("drill_observer_pgbouncer_admin_url_contract_invalid")
    return value


class DisposableDrillObserverEnvironment:
    """Validated child-only environment; representation never contains the URL."""

    __slots__ = ("_environment", "_pgbouncer_container_name", "_redacted_spec")

    def __init__(
        self,
        *,
        environment: Mapping[str, str],
        pgbouncer_container_name: str,
        redacted_spec: Mapping[str, Any],
    ) -> None:
        self._environment = MappingProxyType(dict(environment))
        self._pgbouncer_container_name = pgbouncer_container_name
        self._redacted_spec = MappingProxyType(dict(redacted_spec))

    def __repr__(self) -> str:
        return "DisposableDrillObserverEnvironment(<redacted>)"

    @classmethod
    def from_isolated_preconditions(
        cls,
        config: DisposableDrillBootstrapConfig,
        *,
        base_environment: Mapping[str, str],
    ) -> "DisposableDrillObserverEnvironment":
        config.validate()
        environment: dict[str, str] = {}
        for key in base_environment:
            if key == PGBOUNCER_ADMIN_ENVIRONMENT_KEY:
                raise RuntimeError(
                    "drill_observer_host_pgbouncer_admin_url_environment_forbidden"
                )
            value = base_environment[key]
            if not isinstance(key, str) or not isinstance(value, str):
                raise RuntimeError("drill_observer_executor_environment_invalid")
            environment[key] = value
        assignments = load_postgres_bootstrap_environment(
            config.postgres_environment_path
        )
        if tuple(assignments) != POSTGRES_BOOTSTRAP_ENVIRONMENT_KEYS:
            raise RuntimeError("drill_observer_postgres_environment_order_invalid")
        config_payload = _load_exact_0600_precondition(
            config.pgbouncer_config_path,
            failure="drill_observer_pgbouncer_config",
        )
        userlist_payload = _load_exact_0600_precondition(
            config.pgbouncer_userlist_path,
            failure="drill_observer_pgbouncer_userlist",
        )
        if config_payload != serialize_disposable_pgbouncer_config(assignments):
            raise RuntimeError("drill_observer_pgbouncer_config_readback_mismatch")
        if userlist_payload != serialize_disposable_pgbouncer_userlist(assignments):
            raise RuntimeError("drill_observer_pgbouncer_userlist_readback_mismatch")

        environment[PGBOUNCER_ADMIN_ENVIRONMENT_KEY] = _admin_url(assignments)
        identity = {
            "schema_version": "mindscape.disposable-observer-admin-environment.v1",
            "environment_key": PGBOUNCER_ADMIN_ENVIRONMENT_KEY,
            "environment_key_present": True,
            "source": "canonical_isolated_preconditions",
            "postgres_environment_path": str(config.postgres_environment_path),
            "pgbouncer_config_path": str(config.pgbouncer_config_path),
            "pgbouncer_config_sha256": hashlib.sha256(config_payload).hexdigest(),
            "pgbouncer_userlist_path": str(config.pgbouncer_userlist_path),
            "pgbouncer_userlist_sha256": hashlib.sha256(userlist_payload).hexdigest(),
            "pgbouncer_container_name": config.pgbouncer_container_name,
            "network_contract": "shared_pgbouncer_network_namespace_v1",
            "endpoint_address_class": "loopback",
            "endpoint_port": PGBOUNCER_ADMIN_PORT,
            "endpoint_database": PGBOUNCER_ADMIN_DATABASE,
            "host_environment_value_read": False,
            "host_environment_value_inherited": False,
            "url_or_credential_disclosed": False,
        }
        contract_sha256 = hashlib.sha256(
            json.dumps(identity, sort_keys=True, separators=(",", ":")).encode(
                "utf-8"
            )
        ).hexdigest()
        return cls(
            environment=environment,
            pgbouncer_container_name=config.pgbouncer_container_name,
            redacted_spec={**identity, "contract_sha256": contract_sha256},
        )

    def validate_for(self, pgbouncer_container_name: str) -> None:
        if self._pgbouncer_container_name != pgbouncer_container_name:
            raise ValueError("drill_observer_pgbouncer_environment_identity_mismatch")
        value = self._environment.get(PGBOUNCER_ADMIN_ENVIRONMENT_KEY)
        if not isinstance(value, str) or not value:
            raise ValueError("drill_observer_pgbouncer_admin_url_environment_missing")

    def subprocess_environment(self) -> dict[str, str]:
        return dict(self._environment)

    def executor_environment(self) -> dict[str, str]:
        environment = dict(self._environment)
        environment.pop(PGBOUNCER_ADMIN_ENVIRONMENT_KEY, None)
        return environment

    def redacted_spec(self) -> dict[str, Any]:
        return dict(self._redacted_spec)
