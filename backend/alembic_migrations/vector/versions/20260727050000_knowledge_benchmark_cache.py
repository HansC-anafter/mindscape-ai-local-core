"""Add explicit GraphRAG benchmark catalog, cache, and hit receipts.

Revision ID: 20260727050000
Revises: 20260727042000
Create Date: 2026-07-27
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "20260727050000"
down_revision = "20260727042000"
branch_labels = None
depends_on = None

RUNTIME_ROLE = "mindscape_vector_runtime"
JSONB = postgresql.JSONB(astext_type=sa.Text())
_SCOPE_CHECK = "owner_scope_type IN ('workspace', 'group')"


def _scope_columns() -> tuple[sa.Column, ...]:
    return (
        sa.Column("tenant_id", sa.Text(), nullable=False),
        sa.Column("owner_scope_type", sa.Text(), nullable=False),
        sa.Column("owner_scope_id", sa.Text(), nullable=False),
    )


def _add_scope_policy(table: str, *, append_only: bool = False) -> None:
    op.execute(
        f"""
        ALTER TABLE public.{table} ENABLE ROW LEVEL SECURITY;
        ALTER TABLE public.{table} FORCE ROW LEVEL SECURITY;
        CREATE POLICY knowledge_benchmark_select
        ON public.{table}
        FOR SELECT TO {RUNTIME_ROLE}
        USING (
            tenant_id = current_setting('app.knowledge_tenant', true)
            AND public.knowledge_rls_has_permission(
                'knowledge.read',
                owner_scope_type,
                owner_scope_id
            )
        );
        CREATE POLICY knowledge_benchmark_insert
        ON public.{table}
        FOR INSERT TO {RUNTIME_ROLE}
        WITH CHECK (
            tenant_id = current_setting('app.knowledge_tenant', true)
            AND public.knowledge_rls_has_permission(
                'knowledge.project',
                owner_scope_type,
                owner_scope_id
            )
        );
        """
    )
    if not append_only:
        op.execute(
            f"""
            CREATE POLICY knowledge_benchmark_update
            ON public.{table}
            FOR UPDATE TO {RUNTIME_ROLE}
            USING (
                tenant_id = current_setting(
                    'app.knowledge_tenant',
                    true
                )
                AND public.knowledge_rls_has_permission(
                    'knowledge.project',
                    owner_scope_type,
                    owner_scope_id
                )
            )
            WITH CHECK (
                tenant_id = current_setting(
                    'app.knowledge_tenant',
                    true
                )
                AND public.knowledge_rls_has_permission(
                    'knowledge.project',
                    owner_scope_type,
                    owner_scope_id
                )
            );
            """
        )


def upgrade() -> None:
    op.create_table(
        "knowledge_benchmark_catalogs",
        sa.Column("catalog_revision_id", sa.Text(), primary_key=True),
        *_scope_columns(),
        sa.Column("catalog_id", sa.Text(), nullable=False),
        sa.Column("catalog_revision", sa.Text(), nullable=False),
        sa.Column("dispatch_workspace_id", sa.Text(), nullable=False),
        sa.Column("content_hash", sa.Text(), nullable=False),
        sa.Column("question_count", sa.Integer(), nullable=False),
        sa.Column("created_by_user_id", sa.Text(), nullable=False),
        sa.Column(
            "active",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("TRUE"),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.CheckConstraint(_SCOPE_CHECK, name="ck_kb_catalog_scope"),
        sa.CheckConstraint(
            "char_length(content_hash) = 64",
            name="ck_kb_catalog_content_hash",
        ),
        sa.CheckConstraint(
            "question_count BETWEEN 1 AND 5000",
            name="ck_kb_catalog_question_count",
        ),
        sa.UniqueConstraint(
            "tenant_id",
            "owner_scope_type",
            "owner_scope_id",
            "catalog_id",
            "catalog_revision",
            name="uq_kb_catalog_revision",
        ),
    )
    op.create_index(
        "uq_kb_catalog_active",
        "knowledge_benchmark_catalogs",
        [
            "tenant_id",
            "owner_scope_type",
            "owner_scope_id",
            "catalog_id",
        ],
        unique=True,
        postgresql_where=sa.text("active"),
    )

    op.create_table(
        "knowledge_benchmark_questions",
        sa.Column("question_row_id", sa.Text(), primary_key=True),
        sa.Column(
            "catalog_revision_id",
            sa.Text(),
            sa.ForeignKey(
                "knowledge_benchmark_catalogs.catalog_revision_id",
                ondelete="CASCADE",
            ),
            nullable=False,
        ),
        *_scope_columns(),
        sa.Column("question_id", sa.Text(), nullable=False),
        sa.Column("domain_id", sa.Text(), nullable=False),
        sa.Column("tier", sa.Text(), nullable=False),
        sa.Column("benchmark_class", sa.Text(), nullable=False),
        sa.Column("question_text", sa.Text(), nullable=False),
        sa.Column("canonical_request", JSONB, nullable=False),
        sa.Column("rubric", JSONB, nullable=False),
        sa.Column("question_hash", sa.Text(), nullable=False),
        sa.Column("ordinal", sa.Integer(), nullable=False),
        sa.CheckConstraint(_SCOPE_CHECK, name="ck_kb_question_scope"),
        sa.CheckConstraint(
            "tier IN ('quick', 'contextual', 'cross_domain', "
            "'global_ambiguous')",
            name="ck_kb_question_tier",
        ),
        sa.CheckConstraint(
            "benchmark_class IN ('data_local', 'activity_local', "
            "'data_global', 'activity_global')",
            name="ck_kb_question_class",
        ),
        sa.CheckConstraint(
            "char_length(question_hash) = 64",
            name="ck_kb_question_hash",
        ),
        sa.UniqueConstraint(
            "catalog_revision_id",
            "question_id",
            name="uq_kb_question_id",
        ),
        sa.UniqueConstraint(
            "catalog_revision_id",
            "ordinal",
            name="uq_kb_question_ordinal",
        ),
    )
    op.create_index(
        "idx_kb_questions_domain_tier",
        "knowledge_benchmark_questions",
        ["catalog_revision_id", "domain_id", "tier", "ordinal"],
    )

    op.create_table(
        "knowledge_benchmark_cache_entries",
        sa.Column("cache_key", sa.Text(), primary_key=True),
        sa.Column(
            "question_row_id",
            sa.Text(),
            sa.ForeignKey(
                "knowledge_benchmark_questions.question_row_id",
                ondelete="CASCADE",
            ),
            nullable=False,
        ),
        *_scope_columns(),
        sa.Column("principal_set_hash", sa.Text(), nullable=False),
        sa.Column("request_digest", sa.Text(), nullable=False),
        sa.Column("topology_revision", sa.Text(), nullable=False),
        sa.Column("authorization_generation", sa.Text(), nullable=False),
        sa.Column("projection_digest", sa.Text(), nullable=False),
        sa.Column("response_payload", JSONB, nullable=False),
        sa.Column("resource_bindings", JSONB, nullable=False),
        sa.Column(
            "state",
            sa.Text(),
            nullable=False,
            server_default="active",
        ),
        sa.Column(
            "hit_count",
            sa.BigInteger(),
            nullable=False,
            server_default="0",
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.Column("last_hit_at", sa.DateTime(timezone=True)),
        sa.Column("invalidated_at", sa.DateTime(timezone=True)),
        sa.CheckConstraint(_SCOPE_CHECK, name="ck_kb_cache_scope"),
        sa.CheckConstraint(
            "state IN ('active', 'stale_authorization', "
            "'stale_projection')",
            name="ck_kb_cache_state",
        ),
        sa.CheckConstraint(
            "char_length(principal_set_hash) = 64 "
            "AND char_length(request_digest) = 64 "
            "AND char_length(authorization_generation) = 64 "
            "AND char_length(projection_digest) = 64",
            name="ck_kb_cache_hashes",
        ),
        sa.CheckConstraint(
            "hit_count >= 0",
            name="ck_kb_cache_hit_count",
        ),
    )
    op.create_index(
        "idx_kb_cache_scope_question",
        "knowledge_benchmark_cache_entries",
        [
            "tenant_id",
            "owner_scope_type",
            "owner_scope_id",
            "question_row_id",
            "state",
        ],
    )

    op.create_table(
        "knowledge_benchmark_runs",
        sa.Column("run_id", sa.Text(), primary_key=True),
        sa.Column(
            "question_row_id",
            sa.Text(),
            sa.ForeignKey(
                "knowledge_benchmark_questions.question_row_id",
                ondelete="RESTRICT",
            ),
            nullable=False,
        ),
        sa.Column("cache_key", sa.Text()),
        *_scope_columns(),
        sa.Column("principal_set_hash", sa.Text(), nullable=False),
        sa.Column("cache_status", sa.Text(), nullable=False),
        sa.Column("request_digest", sa.Text(), nullable=False),
        sa.Column("projection_digest", sa.Text(), nullable=False),
        sa.Column("authorization_receipt_digest", sa.Text()),
        sa.Column("latency_ms", sa.Integer(), nullable=False),
        sa.Column("evidence_count", sa.Integer(), nullable=False),
        sa.Column("error_code", sa.Text()),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.CheckConstraint(_SCOPE_CHECK, name="ck_kb_run_scope"),
        sa.CheckConstraint(
            "cache_status IN ('hit', 'miss', 'stale_authorization', "
            "'stale_projection', 'error')",
            name="ck_kb_run_status",
        ),
        sa.CheckConstraint(
            "char_length(principal_set_hash) = 64 "
            "AND char_length(request_digest) = 64 "
            "AND char_length(projection_digest) = 64",
            name="ck_kb_run_hashes",
        ),
        sa.CheckConstraint(
            "latency_ms >= 0 AND evidence_count >= 0",
            name="ck_kb_run_counts",
        ),
    )
    op.create_index(
        "idx_kb_runs_scope_created",
        "knowledge_benchmark_runs",
        [
            "tenant_id",
            "owner_scope_type",
            "owner_scope_id",
            "created_at",
        ],
    )
    op.create_index(
        "idx_kb_runs_question_status",
        "knowledge_benchmark_runs",
        ["question_row_id", "cache_status", "created_at"],
    )

    for table in (
        "knowledge_benchmark_catalogs",
        "knowledge_benchmark_questions",
        "knowledge_benchmark_cache_entries",
    ):
        op.execute(
            f"GRANT SELECT, INSERT, UPDATE ON public.{table} "
            f"TO {RUNTIME_ROLE}"
        )
    op.execute(
        "GRANT SELECT, INSERT ON public.knowledge_benchmark_runs "
        f"TO {RUNTIME_ROLE}"
    )
    _add_scope_policy("knowledge_benchmark_catalogs")
    _add_scope_policy("knowledge_benchmark_questions")
    _add_scope_policy("knowledge_benchmark_cache_entries")
    _add_scope_policy("knowledge_benchmark_runs", append_only=True)


def downgrade() -> None:
    op.drop_table("knowledge_benchmark_runs")
    op.drop_table("knowledge_benchmark_cache_entries")
    op.drop_table("knowledge_benchmark_questions")
    op.drop_table("knowledge_benchmark_catalogs")
