"""
TasksStore — Postgres-backed store for managing task execution records.

Composed from focused mixins:
  _base.py    — CRUD core (create, get, update) + private helpers
  _queries.py — All list_*/find_* read-only query methods
  _runner.py  — Runner lifecycle (claim, heartbeat, zombie reaping, cancel)
"""

from ._base import TasksStoreCrudMixin
from ._queries import TasksStoreQueryMixin
from ._runner import TasksStoreRunnerMixin
from app.services.stores.postgres_base import PostgresStoreBase


class TasksStore(
    TasksStoreRunnerMixin,
    TasksStoreQueryMixin,
    TasksStoreCrudMixin,
    PostgresStoreBase,
):
    """Postgres-backed store for managing task execution records."""

    pass


__all__ = ["TasksStore"]
