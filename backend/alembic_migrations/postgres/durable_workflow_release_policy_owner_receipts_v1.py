"""Corrective DDL leaf for owner-signed durable release policies."""

from __future__ import annotations

OWNER_RECEIPT_COLUMNS = (
    "owner_receipt",
    "canary_receipt",
    "owner_receipt_id",
    "owner_receipt_sha256",
    "trusted_key_registry_revision",
    "trusted_key_registry_sha256",
)

DDL_STATEMENTS = (
    """
    ALTER TABLE durable_workflow_release_policies
        ADD COLUMN owner_receipt JSONB,
        ADD COLUMN canary_receipt JSONB,
        ADD COLUMN owner_receipt_id TEXT,
        ADD COLUMN owner_receipt_sha256 CHAR(64),
        ADD COLUMN trusted_key_registry_revision TEXT,
        ADD COLUMN trusted_key_registry_sha256 CHAR(64)
    """,
    """
    ALTER TABLE durable_workflow_release_policies
    ADD CONSTRAINT ck_durable_workflow_release_policy_owner_receipt_complete
    CHECK (
        num_nonnulls(
            owner_receipt,
            canary_receipt,
            owner_receipt_id,
            owner_receipt_sha256,
            trusted_key_registry_revision,
            trusted_key_registry_sha256
        ) IN (0, 6)
        AND (
            owner_receipt IS NULL
            OR octet_length(owner_receipt::text) <= 65536
        )
        AND (
            canary_receipt IS NULL
            OR octet_length(canary_receipt::text) <= 65536
        )
    ) NOT VALID
    """,
    """
    ALTER TABLE durable_workflow_release_policies
    VALIDATE CONSTRAINT
        ck_durable_workflow_release_policy_owner_receipt_complete
    """,
    """
    CREATE UNIQUE INDEX
        uq_durable_workflow_release_policy_owner_receipt_id
    ON durable_workflow_release_policies (owner_receipt_id)
    WHERE owner_receipt_id IS NOT NULL
    """,
)


def upgrade(op) -> None:
    op.execute("SET LOCAL lock_timeout = '5s'")
    op.execute("SET LOCAL statement_timeout = '120s'")
    for statement in DDL_STATEMENTS:
        op.execute(statement)


def downgrade(op) -> None:
    # Append-only trust evidence is never removed by an automated rollback.
    op.execute("SELECT 1")
