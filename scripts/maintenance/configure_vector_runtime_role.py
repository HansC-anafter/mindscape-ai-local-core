#!/usr/bin/env python3
"""Bounded credential gate for the existing vector runtime role."""

from __future__ import annotations

import argparse
import json
import os
from urllib.parse import urlsplit

import psycopg2


ROLE = "mindscape_vector_runtime"
PERMIT = "authorization-aware-graphrag-t07-20260727"


def _session_url() -> str:
    value = os.getenv("DATABASE_URL_VECTOR_SESSION", "")
    parsed = urlsplit(value)
    if (
        parsed.scheme not in {"postgres", "postgresql"}
        or not parsed.hostname
        or parsed.port not in {None, 5432}
        or parsed.hostname == "pgbouncer"
    ):
        raise RuntimeError("vector_runtime_role_owner_session_url_required")
    return value


def _readback(connection) -> dict[str, object]:
    cursor = connection.cursor()
    cursor.execute(
        """
        SELECT
            rolname,
            rolcanlogin,
            rolsuper,
            rolcreatedb,
            rolcreaterole,
            rolinherit,
            rolbypassrls,
            rolpassword IS NOT NULL
        FROM pg_roles
        WHERE rolname = %s
        """,
        (ROLE,),
    )
    row = cursor.fetchone()
    if row is None:
        return {"role": ROLE, "present": False}
    return {
        "role": str(row[0]),
        "present": True,
        "login": bool(row[1]),
        "superuser": bool(row[2]),
        "createdb": bool(row[3]),
        "createrole": bool(row[4]),
        "inherit": bool(row[5]),
        "bypassrls": bool(row[6]),
        "password_configured": bool(row[7]),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--permit-id")
    args = parser.parse_args()

    connection = psycopg2.connect(_session_url())
    try:
        before = _readback(connection)
        if args.apply:
            if args.permit_id != PERMIT:
                raise RuntimeError("vector_runtime_role_permit_invalid")
            if not before.get("present"):
                raise RuntimeError("vector_runtime_role_migration_required")
            password = os.getenv("POSTGRES_VECTOR_RUNTIME_PASSWORD", "")
            if not password:
                raise RuntimeError(
                    "vector_runtime_role_password_environment_required"
                )
            cursor = connection.cursor()
            cursor.execute(
                f"""
                ALTER ROLE {ROLE}
                    LOGIN
                    NOSUPERUSER
                    NOCREATEDB
                    NOCREATEROLE
                    NOINHERIT
                    NOBYPASSRLS
                    PASSWORD %s
                """,
                (password,),
            )
            connection.commit()
        after = _readback(connection)
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()

    passed = bool(
        after.get("present")
        and after.get("login")
        and not after.get("superuser")
        and not after.get("createdb")
        and not after.get("createrole")
        and not after.get("inherit")
        and not after.get("bypassrls")
        and (not args.apply or after.get("password_configured"))
    )
    print(
        json.dumps(
            {
                "contract_version": "vector_runtime_role_gate.v1",
                "mode": "apply" if args.apply else "check",
                "permit_id": args.permit_id if args.apply else None,
                "before": before,
                "after": after,
                "gate_pass": passed,
            },
            sort_keys=True,
        )
    )
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
