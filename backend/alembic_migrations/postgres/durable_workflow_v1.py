"""Immutable PostgreSQL DDL leaf for durable workflow v1."""

from __future__ import annotations

TABLE_NAMES = (
    "durable_workflow_instances",
    "durable_workflow_events",
    "durable_workflow_checkpoints",
    "durable_workflow_approval_requests",
    "durable_workflow_approval_decisions",
    "durable_workflow_approval_consumptions",
    "durable_workflow_side_effect_receipts",
    "durable_workflow_projection_offsets",
    "durable_workflow_integrity_anchors",
    "durable_workflow_release_policies",
)

DDL_STATEMENTS = (
    """
    CREATE TABLE durable_workflow_instances (
        workflow_id TEXT PRIMARY KEY,
        root_workflow_id TEXT NOT NULL,
        segment_id TEXT NOT NULL UNIQUE,
        segment_number INTEGER NOT NULL CHECK (segment_number >= 0),
        predecessor_segment_id TEXT,
        predecessor_terminal_hash CHAR(64),
        workflow_kind TEXT NOT NULL
            CHECK (workflow_kind IN ('execution', 'product_iteration', 'product_release')),
        workspace_id TEXT NOT NULL,
        execution_id TEXT,
        psc_ids JSONB NOT NULL,
        semantic_identity JSONB NOT NULL,
        semantic_identity_hash CHAR(64) NOT NULL,
        current_sequence BIGINT NOT NULL DEFAULT 0 CHECK (current_sequence >= 0),
        current_event_hash CHAR(64),
        current_state TEXT NOT NULL,
        terminal BOOLEAN NOT NULL DEFAULT FALSE,
        workflow_definition_version TEXT NOT NULL,
        reducer_version TEXT NOT NULL,
        effect_adapter_registry_version TEXT NOT NULL,
        runtime_build_id TEXT NOT NULL,
        replay_compatibility_class TEXT NOT NULL,
        event_count INTEGER NOT NULL DEFAULT 0
            CHECK (event_count BETWEEN 0 AND 10000),
        canonical_event_bytes BIGINT NOT NULL DEFAULT 0
            CHECK (canonical_event_bytes BETWEEN 0 AND 67108864),
        next_durable_deadline TIMESTAMPTZ,
        cancellation_state TEXT,
        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        CHECK (jsonb_typeof(psc_ids) = 'array'),
        CHECK (octet_length(semantic_identity::text) <= 16384),
        CHECK (
            (segment_number = 0 AND predecessor_segment_id IS NULL
                AND predecessor_terminal_hash IS NULL)
            OR
            (segment_number > 0 AND predecessor_segment_id IS NOT NULL
                AND predecessor_terminal_hash IS NOT NULL)
        ),
        UNIQUE (root_workflow_id, segment_number)
    )
    """,
    """
    CREATE TABLE durable_workflow_events (
        event_id TEXT PRIMARY KEY,
        workflow_id TEXT NOT NULL
            REFERENCES durable_workflow_instances(workflow_id) ON DELETE RESTRICT,
        segment_id TEXT NOT NULL,
        sequence BIGINT NOT NULL CHECK (sequence >= 1),
        event_type TEXT NOT NULL,
        idempotency_key TEXT NOT NULL,
        timer_id TEXT,
        external_message_id TEXT,
        actor JSONB NOT NULL,
        payload JSONB NOT NULL,
        payload_sha256 CHAR(64) NOT NULL,
        previous_event_hash CHAR(64),
        event_hash CHAR(64) NOT NULL,
        canonical_bytes INTEGER NOT NULL
            CHECK (canonical_bytes BETWEEN 2 AND 16384),
        occurred_at TIMESTAMPTZ NOT NULL,
        key_id TEXT NOT NULL,
        signature TEXT NOT NULL,
        CHECK (octet_length(actor::text) <= 4096),
        CHECK (octet_length(payload::text) <= 16384),
        UNIQUE (workflow_id, sequence),
        UNIQUE (workflow_id, idempotency_key)
    )
    """,
    """
    CREATE TABLE durable_workflow_checkpoints (
        checkpoint_id TEXT PRIMARY KEY,
        workflow_id TEXT NOT NULL
            REFERENCES durable_workflow_instances(workflow_id) ON DELETE RESTRICT,
        sequence BIGINT NOT NULL CHECK (sequence >= 0),
        parent_checkpoint_id TEXT
            REFERENCES durable_workflow_checkpoints(checkpoint_id) ON DELETE RESTRICT,
        state_hash CHAR(64) NOT NULL,
        event_hash CHAR(64) NOT NULL,
        reducer_version TEXT NOT NULL,
        payload JSONB NOT NULL,
        key_id TEXT NOT NULL,
        signature TEXT NOT NULL,
        created_at TIMESTAMPTZ NOT NULL,
        CHECK (octet_length(payload::text) <= 16384),
        UNIQUE (workflow_id, sequence)
    )
    """,
    """
    CREATE TABLE durable_workflow_approval_requests (
        approval_id TEXT PRIMARY KEY,
        workflow_id TEXT NOT NULL
            REFERENCES durable_workflow_instances(workflow_id) ON DELETE RESTRICT,
        interrupt_id TEXT NOT NULL,
        tool_call_id TEXT NOT NULL,
        action_hash CHAR(64) NOT NULL,
        resume_payload_hash CHAR(64) NOT NULL,
        requested_by TEXT NOT NULL,
        required_quorum INTEGER NOT NULL DEFAULT 1
            CHECK (required_quorum BETWEEN 1 AND 20),
        separation_of_duties BOOLEAN NOT NULL DEFAULT FALSE,
        payload JSONB NOT NULL,
        expires_at TIMESTAMPTZ NOT NULL,
        key_id TEXT NOT NULL,
        signature TEXT NOT NULL,
        created_at TIMESTAMPTZ NOT NULL,
        CHECK (octet_length(payload::text) <= 16384),
        UNIQUE (workflow_id, interrupt_id, tool_call_id, action_hash)
    )
    """,
    """
    CREATE TABLE durable_workflow_approval_decisions (
        decision_id TEXT PRIMARY KEY,
        approval_id TEXT NOT NULL
            REFERENCES durable_workflow_approval_requests(approval_id) ON DELETE RESTRICT,
        decided_by TEXT NOT NULL,
        decision TEXT NOT NULL
            CHECK (decision IN ('approved', 'rejected', 'expired', 'revoked')),
        policy_version TEXT NOT NULL,
        payload JSONB NOT NULL,
        key_id TEXT NOT NULL,
        signature TEXT NOT NULL,
        decided_at TIMESTAMPTZ NOT NULL,
        CHECK (octet_length(payload::text) <= 16384),
        UNIQUE (approval_id, decided_by)
    )
    """,
    """
    CREATE TABLE durable_workflow_approval_consumptions (
        consumption_id TEXT PRIMARY KEY,
        approval_id TEXT NOT NULL
            REFERENCES durable_workflow_approval_requests(approval_id) ON DELETE RESTRICT,
        decision_id TEXT NOT NULL
            REFERENCES durable_workflow_approval_decisions(decision_id) ON DELETE RESTRICT,
        delivery_id TEXT NOT NULL,
        effect_or_transition_id TEXT NOT NULL,
        payload JSONB NOT NULL,
        key_id TEXT NOT NULL,
        signature TEXT NOT NULL,
        consumed_at TIMESTAMPTZ NOT NULL,
        CHECK (octet_length(payload::text) <= 16384),
        UNIQUE (approval_id),
        UNIQUE (delivery_id),
        UNIQUE (effect_or_transition_id)
    )
    """,
    """
    CREATE TABLE durable_workflow_side_effect_receipts (
        receipt_id TEXT PRIMARY KEY,
        workflow_id TEXT NOT NULL
            REFERENCES durable_workflow_instances(workflow_id) ON DELETE RESTRICT,
        effect_id TEXT NOT NULL,
        effect_type TEXT NOT NULL,
        owner TEXT NOT NULL,
        request_hash CHAR(64) NOT NULL,
        response_hash CHAR(64),
        adapter_id TEXT NOT NULL,
        adapter_version TEXT NOT NULL,
        status TEXT NOT NULL
            CHECK (status IN ('prepared', 'succeeded', 'failed', 'compensated')),
        replay_disposition TEXT NOT NULL,
        attempt INTEGER NOT NULL CHECK (attempt >= 1),
        payload JSONB NOT NULL,
        key_id TEXT NOT NULL,
        signature TEXT NOT NULL,
        recorded_at TIMESTAMPTZ NOT NULL,
        CHECK (octet_length(payload::text) <= 16384),
        UNIQUE (workflow_id, effect_id, owner, attempt)
    )
    """,
    """
    CREATE TABLE durable_workflow_projection_offsets (
        projection_name TEXT NOT NULL,
        workflow_id TEXT NOT NULL
            REFERENCES durable_workflow_instances(workflow_id) ON DELETE RESTRICT,
        last_sequence BIGINT NOT NULL CHECK (last_sequence >= 0),
        reducer_version TEXT NOT NULL,
        state_hash CHAR(64) NOT NULL,
        state JSONB NOT NULL,
        updated_at TIMESTAMPTZ NOT NULL,
        CHECK (octet_length(state::text) <= 16384),
        PRIMARY KEY (projection_name, workflow_id)
    )
    """,
    """
    CREATE TABLE durable_workflow_integrity_anchors (
        anchor_id TEXT PRIMARY KEY,
        workflow_id TEXT NOT NULL
            REFERENCES durable_workflow_instances(workflow_id) ON DELETE RESTRICT,
        start_sequence BIGINT NOT NULL CHECK (start_sequence >= 1),
        end_sequence BIGINT NOT NULL CHECK (end_sequence >= start_sequence),
        merkle_root CHAR(64) NOT NULL,
        key_id TEXT NOT NULL,
        public_key_fingerprint CHAR(64) NOT NULL,
        signature TEXT NOT NULL,
        object_ref JSONB,
        object_immutability_receipt JSONB,
        created_at TIMESTAMPTZ NOT NULL,
        CHECK (object_ref IS NULL OR octet_length(object_ref::text) <= 4096),
        CHECK (
            object_immutability_receipt IS NULL
            OR octet_length(object_immutability_receipt::text) <= 4096
        ),
        UNIQUE (workflow_id, start_sequence, end_sequence)
    )
    """,
    """
    CREATE TABLE durable_workflow_release_policies (
        workspace_id TEXT NOT NULL,
        workflow_kind TEXT NOT NULL
            CHECK (workflow_kind IN ('execution', 'product_iteration', 'product_release')),
        revision BIGINT NOT NULL CHECK (revision >= 1),
        supersedes_revision BIGINT,
        mode TEXT NOT NULL CHECK (mode IN ('disabled', 'shadow', 'enforced')),
        policy JSONB NOT NULL,
        policy_hash CHAR(64) NOT NULL,
        key_id TEXT NOT NULL,
        signature TEXT NOT NULL,
        created_by TEXT NOT NULL,
        created_at TIMESTAMPTZ NOT NULL,
        CHECK (octet_length(policy::text) <= 16384),
        CHECK (
            (revision = 1 AND supersedes_revision IS NULL)
            OR supersedes_revision = revision - 1
        ),
        PRIMARY KEY (workspace_id, workflow_kind, revision)
    )
    """,
    """
    CREATE UNIQUE INDEX uq_durable_workflow_timer_id
    ON durable_workflow_events (workflow_id, timer_id)
    WHERE timer_id IS NOT NULL
    """,
    """
    CREATE UNIQUE INDEX uq_durable_workflow_external_message_id
    ON durable_workflow_events (workflow_id, external_message_id)
    WHERE external_message_id IS NOT NULL
    """,
    """
    CREATE UNIQUE INDEX uq_durable_workflow_effect_terminal_owner
    ON durable_workflow_side_effect_receipts (workflow_id, effect_id, owner)
    WHERE status IN ('succeeded', 'compensated')
    """,
    """
    CREATE INDEX idx_durable_workflow_workspace_execution
    ON durable_workflow_instances (workspace_id, execution_id)
    WHERE execution_id IS NOT NULL
    """,
    """
    CREATE INDEX idx_durable_workflow_workspace_state
    ON durable_workflow_instances (
        workspace_id, workflow_kind, terminal, current_state, updated_at DESC
    )
    """,
    """
    CREATE INDEX idx_durable_workflow_root_segments
    ON durable_workflow_instances (root_workflow_id, segment_number)
    """,
    """
    CREATE INDEX idx_durable_workflow_events_keyset
    ON durable_workflow_events (workflow_id, sequence)
    """,
    """
    CREATE UNIQUE INDEX uq_durable_workflow_terminal_receipt_id
    ON durable_workflow_events (
        (payload #>> '{typed_receipt,receipt,receipt_id}')
    )
    WHERE event_type = 'transition'
      AND payload #>> '{typed_receipt,receipt_type}'
          = 'execution_terminal_receipt'
    """,
    """
    CREATE UNIQUE INDEX uq_durable_workflow_enrollment_terminal_receipt
    ON durable_workflow_events (
        (payload #>> '{enrollment,terminal_receipt_id}')
    )
    WHERE event_type = 'iteration_enrollment_accepted'
    """,
    """
    CREATE INDEX idx_durable_workflow_deadlines
    ON durable_workflow_instances (next_durable_deadline, workflow_id)
    WHERE next_durable_deadline IS NOT NULL AND terminal = FALSE
    """,
    """
    CREATE INDEX idx_durable_workflow_approval_pending
    ON durable_workflow_approval_requests (workflow_id, expires_at, approval_id)
    """,
    """
    CREATE OR REPLACE FUNCTION reject_durable_workflow_immutable_mutation()
    RETURNS trigger
    LANGUAGE plpgsql
    AS $$
    BEGIN
        RAISE EXCEPTION '% is insert-only; use an append-only corrective receipt', TG_TABLE_NAME;
    END;
    $$
    """,
    """
    CREATE TRIGGER immutable_durable_workflow_events
    BEFORE UPDATE OR DELETE ON durable_workflow_events
    FOR EACH ROW EXECUTE FUNCTION reject_durable_workflow_immutable_mutation()
    """,
    """
    CREATE TRIGGER immutable_durable_workflow_checkpoints
    BEFORE UPDATE OR DELETE ON durable_workflow_checkpoints
    FOR EACH ROW EXECUTE FUNCTION reject_durable_workflow_immutable_mutation()
    """,
    """
    CREATE TRIGGER immutable_durable_workflow_approval_requests
    BEFORE UPDATE OR DELETE ON durable_workflow_approval_requests
    FOR EACH ROW EXECUTE FUNCTION reject_durable_workflow_immutable_mutation()
    """,
    """
    CREATE TRIGGER immutable_durable_workflow_approval_decisions
    BEFORE UPDATE OR DELETE ON durable_workflow_approval_decisions
    FOR EACH ROW EXECUTE FUNCTION reject_durable_workflow_immutable_mutation()
    """,
    """
    CREATE TRIGGER immutable_durable_workflow_approval_consumptions
    BEFORE UPDATE OR DELETE ON durable_workflow_approval_consumptions
    FOR EACH ROW EXECUTE FUNCTION reject_durable_workflow_immutable_mutation()
    """,
    """
    CREATE TRIGGER immutable_durable_workflow_side_effect_receipts
    BEFORE UPDATE OR DELETE ON durable_workflow_side_effect_receipts
    FOR EACH ROW EXECUTE FUNCTION reject_durable_workflow_immutable_mutation()
    """,
    """
    CREATE TRIGGER immutable_durable_workflow_integrity_anchors
    BEFORE UPDATE OR DELETE ON durable_workflow_integrity_anchors
    FOR EACH ROW EXECUTE FUNCTION reject_durable_workflow_immutable_mutation()
    """,
    """
    CREATE TRIGGER immutable_durable_workflow_release_policies
    BEFORE UPDATE OR DELETE ON durable_workflow_release_policies
    FOR EACH ROW EXECUTE FUNCTION reject_durable_workflow_immutable_mutation()
    """,
)


def upgrade(op_module) -> None:
    op_module.execute("SET LOCAL lock_timeout = '5s'")
    op_module.execute("SET LOCAL statement_timeout = '30s'")
    for statement in DDL_STATEMENTS:
        op_module.execute(statement)


def downgrade(_op_module) -> None:
    raise RuntimeError(
        "durable workflow v1 is append-only; use a forward-fix migration"
    )
