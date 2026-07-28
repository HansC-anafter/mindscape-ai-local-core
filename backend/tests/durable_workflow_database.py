"""Shared isolated-PostgreSQL fixture for durable workflow specifications."""

from __future__ import annotations

import os

import pytest
from sqlalchemy import create_engine

from alembic_migrations.postgres import (
    durable_workflow_release_policy_owner_receipts_v1,
    durable_workflow_v1,
)


@pytest.fixture(scope="session")
def engine():
    dsn = os.environ.get("DURABLE_WORKFLOW_TEST_DATABASE_URL")
    if not dsn:
        pytest.skip("isolated PostgreSQL URL is required")
    created = create_engine(dsn, pool_size=4, max_overflow=0)
    with created.begin() as conn:
        class Op:
            @staticmethod
            def execute(statement):
                conn.exec_driver_sql(statement)

        durable_workflow_v1.upgrade(Op)
        durable_workflow_release_policy_owner_receipts_v1.upgrade(Op)
    yield created
    created.dispose()
