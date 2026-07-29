"""Admit graph-entity conflict resolution only inside a verified write scope.

Revision ID: 20260727042000
Revises: 20260727041000
Create Date: 2026-07-27
"""

from __future__ import annotations

from alembic import op


revision = "20260727042000"
down_revision = "20260727041000"
branch_labels = None
depends_on = None

RUNTIME_ROLE = "mindscape_vector_runtime"


def _create_write_scope_function() -> None:
    op.execute(
        """
        CREATE OR REPLACE FUNCTION
            public.knowledge_rls_entity_in_write_scope(
                requested_tenant_id text,
                requested_scope_type text,
                requested_scope_id text
            )
        RETURNS boolean
        LANGUAGE sql
        STABLE
        SECURITY DEFINER
        SET search_path = pg_catalog, pg_temp
        SET row_security = off
        AS $function$
            SELECT
                public.knowledge_rls_write_scope_allowed()
                AND requested_tenant_id = current_setting(
                    'app.knowledge_tenant',
                    true
                )
                AND requested_scope_type = current_setting(
                    'app.knowledge_write_scope_type',
                    true
                )
                AND requested_scope_id = current_setting(
                    'app.knowledge_write_scope_id',
                    true
                )
        $function$
        """
    )
    op.execute(
        f"""
        REVOKE ALL ON FUNCTION
            public.knowledge_rls_entity_in_write_scope(text, text, text)
        FROM PUBLIC;
        GRANT EXECUTE ON FUNCTION
            public.knowledge_rls_entity_in_write_scope(text, text, text)
        TO {RUNTIME_ROLE};
        """
    )


def _create_scoped_policies() -> None:
    op.execute(
        f"""
        DROP POLICY IF EXISTS knowledge_runtime_select
            ON public.knowledge_graph_entities;
        DROP POLICY IF EXISTS knowledge_runtime_insert
            ON public.knowledge_graph_entities;
        CREATE POLICY knowledge_runtime_select
        ON public.knowledge_graph_entities
        FOR SELECT
        TO {RUNTIME_ROLE}
        USING (
            public.knowledge_rls_can_access_entity(entity_id)
            OR public.knowledge_rls_entity_in_write_scope(
                tenant_id,
                scope_type,
                scope_id
            )
        );
        CREATE POLICY knowledge_runtime_insert
        ON public.knowledge_graph_entities
        FOR INSERT
        TO {RUNTIME_ROLE}
        WITH CHECK (
            public.knowledge_rls_entity_in_write_scope(
                tenant_id,
                scope_type,
                scope_id
            )
        );
        """
    )


def upgrade() -> None:
    _create_write_scope_function()
    _create_scoped_policies()


def downgrade() -> None:
    op.execute(
        f"""
        DROP POLICY IF EXISTS knowledge_runtime_select
            ON public.knowledge_graph_entities;
        DROP POLICY IF EXISTS knowledge_runtime_insert
            ON public.knowledge_graph_entities;
        CREATE POLICY knowledge_runtime_select
        ON public.knowledge_graph_entities
        FOR SELECT
        TO {RUNTIME_ROLE}
        USING (
            public.knowledge_rls_can_access_entity(entity_id)
        );
        CREATE POLICY knowledge_runtime_insert
        ON public.knowledge_graph_entities
        FOR INSERT
        TO {RUNTIME_ROLE}
        WITH CHECK (
            public.knowledge_rls_write_scope_allowed()
        );
        DROP FUNCTION IF EXISTS
            public.knowledge_rls_entity_in_write_scope(text, text, text);
        """
    )
