"""Forward-only indexed lookup DDL for durable outcome evidence."""

from __future__ import annotations

DDL_STATEMENTS = (
    """
    CREATE UNIQUE INDEX IF NOT EXISTS
        uq_durable_workflow_terminal_receipt_id
    ON durable_workflow_events (
        (payload #>> '{typed_receipt,receipt,receipt_id}')
    )
    WHERE event_type = 'transition'
      AND payload #>> '{typed_receipt,receipt_type}'
          = 'execution_terminal_receipt'
    """,
    """
    CREATE UNIQUE INDEX IF NOT EXISTS
        uq_durable_workflow_enrollment_terminal_receipt
    ON durable_workflow_events (
        (payload #>> '{enrollment,terminal_receipt_id}')
    )
    WHERE event_type = 'iteration_enrollment_accepted'
    """,
)


def upgrade(op_module) -> None:
    op_module.execute("SET LOCAL lock_timeout = '5s'")
    op_module.execute("SET LOCAL statement_timeout = '30s'")
    for statement in DDL_STATEMENTS:
        op_module.execute(statement)


def downgrade(_op_module) -> None:
    raise RuntimeError(
        "durable outcome lookup indexes are forward-only; " "use a reviewed forward fix"
    )
