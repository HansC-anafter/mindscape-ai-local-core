"""Bounded, read-only runtime schema readiness aggregation."""

from __future__ import annotations

import threading
import time
from pathlib import Path
from typing import Any, Callable

from sqlalchemy import text

from backend.app.services.host_resources.schema_readiness import (
    check_host_resource_schema_readiness,
)
from backend.app.services.migrations import MigrationOrchestrator
from backend.app.services.migrations.database_plan import authoritative_alembic_configs
from backend.app.services.stores.postgres_base import PostgresStoreBase

from .contracts import ACCESS_TABLES, RUNTIME_UPGRADE_COMMAND


class RuntimeSchemaHealthFacade:
    """Compose runtime schema diagnostics without performing migrations."""

    def __init__(
        self,
        *,
        host_resource_reporter: Callable[[], dict[str, Any]] | None = None,
        migration_reporter: Callable[[], dict[str, Any]] | None = None,
        access_reporter: Callable[[], dict[str, bool]] | None = None,
        ttl_seconds: float = 30.0,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._host_resource_reporter = (
            host_resource_reporter or check_host_resource_schema_readiness
        )
        self._migration_reporter = migration_reporter or self._migration_report
        self._access_reporter = access_reporter or self._access_report
        self._ttl_seconds = max(float(ttl_seconds), 0.0)
        self._clock = clock
        self._lock = threading.Lock()
        self._cached_at = float("-inf")
        self._cached: dict[str, Any] | None = None

    def inspect(self, *, force: bool = False) -> dict[str, Any]:
        now = self._clock()
        with self._lock:
            if (
                not force
                and self._cached is not None
                and now - self._cached_at < self._ttl_seconds
            ):
                return dict(self._cached)
            report = self._compute()
            self._cached = report
            self._cached_at = now
            return dict(report)

    def _compute(self) -> dict[str, Any]:
        try:
            host_resources = self._host_resource_reporter()
            migrations = self._migration_reporter()
            access_tables = self._access_reporter()
            catalog_ready = migrations.get("status") in {
                "success",
                "no_migrations",
            }
            access_ready = all(access_tables.get(name, False) for name in ACCESS_TABLES)
            ready = bool(
                host_resources.get("ready", False)
                and catalog_ready
                and access_ready
            )
            return {
                "ready": ready,
                "scope": "runtime-operational-schema",
                "catalog_ready": catalog_ready,
                "catalog_status": migrations.get("status", "error"),
                "catalog_error": migrations.get("error"),
                "unresolved_current_heads": migrations.get(
                    "unresolved_current_heads",
                    [],
                ),
                "access_ready": access_ready,
                "access_tables": access_tables,
                "host_resources_ready": host_resources.get("ready", False),
                "host_resources_scope": host_resources.get(
                    "scope",
                    "host-resource-only",
                ),
                "upgrade_command": RUNTIME_UPGRADE_COMMAND,
                "error": None,
            }
        except Exception as exc:
            return {
                "ready": False,
                "scope": "runtime-operational-schema",
                "catalog_ready": False,
                "access_ready": False,
                "host_resources_ready": False,
                "upgrade_command": RUNTIME_UPGRADE_COMMAND,
                "error": str(exc),
            }

    @staticmethod
    def _migration_report() -> dict[str, Any]:
        backend_dir = Path(__file__).resolve().parents[3]
        orchestrator = MigrationOrchestrator(
            backend_dir / "app" / "capabilities",
            authoritative_alembic_configs(backend_dir),
        )
        return orchestrator.dry_run("postgres")

    @staticmethod
    def _access_report() -> dict[str, bool]:
        with PostgresStoreBase("core").get_connection() as conn:
            return {
                table_name: bool(
                    conn.execute(
                        text("SELECT to_regclass(:name) IS NOT NULL"),
                        {"name": f"public.{table_name}"},
                    ).scalar()
                )
                for table_name in ACCESS_TABLES
            }
