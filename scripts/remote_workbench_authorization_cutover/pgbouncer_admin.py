"""Build the single authenticated PgBouncer admin command path."""

from __future__ import annotations

from .io import CutoverError


_ALLOWED_QUERIES = frozenset({"SHOW CONFIG;", "SHOW POOLS;"})
_CONTAINER = "mindscape-ai-local-core-pgbouncer"
_AUTHENTICATED_EXEC = 'PGPASSWORD="$POSTGRES_CORE_PASSWORD" exec "$@"'


def pgbouncer_admin_csv_command(query: str) -> list[str]:
    """Return a fixed CSV admin command without exposing the container secret."""

    if query not in _ALLOWED_QUERIES:
        raise CutoverError("PgBouncer admin query is not allowlisted")
    return [
        "docker",
        "exec",
        _CONTAINER,
        "sh",
        "-c",
        _AUTHENTICATED_EXEC,
        "pgbouncer-admin",
        "psql",
        "-X",
        "--no-password",
        "-v",
        "ON_ERROR_STOP=1",
        "-U",
        "mindscape",
        "-h",
        "127.0.0.1",
        "-p",
        "6432",
        "-d",
        "pgbouncer",
        "--csv",
        "-c",
        query,
    ]
