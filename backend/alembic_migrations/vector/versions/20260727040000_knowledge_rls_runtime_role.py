"""Add the non-owner vector runtime role and knowledge RLS policies.

Revision ID: 20260727040000
Revises: 20260727036000
"""

from __future__ import annotations

from alembic import op


revision = "20260727040000"
down_revision = "20260727036000"
branch_labels = None
depends_on = None


RUNTIME_ROLE = "mindscape_vector_runtime"

FULL_DML_TABLES = (
    "external_docs",
    "knowledge_embedding_channel_receipts",
    "knowledge_evidence_units",
    "knowledge_graph_communities",
    "knowledge_graph_community_memberships",
    "knowledge_graph_community_reports",
    "knowledge_graph_mentions",
    "knowledge_graph_relations",
    "knowledge_projection_facets",
    "knowledge_projection_records",
    "knowledge_resource_agent_masks",
    "knowledge_resource_projections",
    "knowledge_resources",
    "knowledge_security_label_grants",
    "knowledge_security_labels",
    "mindscape_personal",
    "mindscape_suggestions",
    "playbook_knowledge",
    "tool_embeddings",
    "video_segments",
    "voice_profiles",
    "voice_training_jobs",
)
APPEND_ONLY_TABLES = (
    "knowledge_acl_audit_log",
    "knowledge_agent_mask_audit_log",
    "knowledge_graph_entities",
)
RLS_TABLES = (
    "external_docs",
    "knowledge_acl_audit_log",
    "knowledge_agent_mask_audit_log",
    "knowledge_embedding_channel_receipts",
    "knowledge_evidence_units",
    "knowledge_graph_communities",
    "knowledge_graph_community_memberships",
    "knowledge_graph_community_reports",
    "knowledge_graph_entities",
    "knowledge_graph_mentions",
    "knowledge_graph_relations",
    "knowledge_projection_facets",
    "knowledge_projection_records",
    "knowledge_resource_agent_masks",
    "knowledge_resource_projections",
    "knowledge_resources",
    "knowledge_security_label_grants",
    "knowledge_security_labels",
)


def _create_role_and_privileges() -> None:
    op.execute(
        f"""
        DO $role$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM pg_roles WHERE rolname = '{RUNTIME_ROLE}'
            ) THEN
                CREATE ROLE {RUNTIME_ROLE}
                    LOGIN
                    NOSUPERUSER
                    NOCREATEDB
                    NOCREATEROLE
                    NOINHERIT
                    NOBYPASSRLS;
            ELSE
                ALTER ROLE {RUNTIME_ROLE}
                    LOGIN
                    NOSUPERUSER
                    NOCREATEDB
                    NOCREATEROLE
                    NOINHERIT
                    NOBYPASSRLS;
            END IF;
        END
        $role$;
        """
    )
    op.execute(f"GRANT USAGE ON SCHEMA public TO {RUNTIME_ROLE}")
    for table in FULL_DML_TABLES:
        op.execute(
            f"""
            DO $grant$
            BEGIN
                IF to_regclass('public.{table}') IS NOT NULL THEN
                    GRANT SELECT, INSERT, UPDATE, DELETE
                    ON TABLE public.{table} TO {RUNTIME_ROLE};
                END IF;
            END
            $grant$;
            """
        )
    for table in APPEND_ONLY_TABLES:
        op.execute(
            f"""
            DO $grant$
            BEGIN
                IF to_regclass('public.{table}') IS NOT NULL THEN
                    GRANT SELECT, INSERT
                    ON TABLE public.{table} TO {RUNTIME_ROLE};
                END IF;
            END
            $grant$;
            """
        )
    table_names = ", ".join(
        f"'{table}'" for table in (*FULL_DML_TABLES, *APPEND_ONLY_TABLES)
    )
    op.execute(
        f"""
        DO $grant_sequences$
        DECLARE
            sequence_row record;
        BEGIN
            FOR sequence_row IN
                SELECT DISTINCT
                    quote_ident(sequence_namespace.nspname) || '.' ||
                    quote_ident(sequence_class.relname) AS qualified_name
                FROM pg_class AS sequence_class
                JOIN pg_namespace AS sequence_namespace
                  ON sequence_namespace.oid =
                     sequence_class.relnamespace
                JOIN pg_depend AS dependency
                  ON dependency.objid = sequence_class.oid
                 AND dependency.deptype IN ('a', 'i')
                JOIN pg_class AS table_class
                  ON table_class.oid = dependency.refobjid
                JOIN pg_namespace AS table_namespace
                  ON table_namespace.oid = table_class.relnamespace
                WHERE sequence_class.relkind = 'S'
                  AND table_namespace.nspname = 'public'
                  AND table_class.relname IN ({table_names})
            LOOP
                EXECUTE 'GRANT USAGE, SELECT ON SEQUENCE ' ||
                        sequence_row.qualified_name ||
                        ' TO {RUNTIME_ROLE}';
            END LOOP;
        END
        $grant_sequences$;
        """
    )


def _create_context_functions() -> None:
    op.execute(
        """
        CREATE OR REPLACE FUNCTION public.knowledge_rls_has_permission(
            permission_name text,
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
                NULLIF(
                    current_setting(
                        'app.knowledge_permissions_json',
                        true
                    ),
                    ''
                ) IS NOT NULL
                AND EXISTS (
                    SELECT 1
                    FROM jsonb_to_recordset(
                        current_setting(
                            'app.knowledge_permissions_json',
                            true
                        )::jsonb
                    ) AS permission(
                        name text,
                        scope_type text,
                        scope_id text
                    )
                    WHERE permission.name = permission_name
                      AND permission.scope_type = requested_scope_type
                      AND permission.scope_id = requested_scope_id
                )
        $function$
        """
    )
    op.execute(
        """
        CREATE OR REPLACE FUNCTION public.knowledge_rls_write_scope_allowed()
        RETURNS boolean
        LANGUAGE sql
        STABLE
        SECURITY DEFINER
        SET search_path = pg_catalog, pg_temp
        SET row_security = off
        AS $function$
            SELECT
                NULLIF(
                    current_setting('app.knowledge_tenant', true),
                    ''
                ) IS NOT NULL
                AND NULLIF(
                    current_setting(
                        'app.knowledge_write_scope_type',
                        true
                    ),
                    ''
                ) IS NOT NULL
                AND NULLIF(
                    current_setting(
                        'app.knowledge_write_scope_id',
                        true
                    ),
                    ''
                ) IS NOT NULL
                AND NULLIF(
                    current_setting(
                        'app.knowledge_write_resource_id',
                        true
                    ),
                    ''
                ) IS NOT NULL
                AND NULLIF(
                    current_setting(
                        'app.knowledge_write_security_label_id',
                        true
                    ),
                    ''
                ) IS NOT NULL
                AND (
                    public.knowledge_rls_has_permission(
                        'knowledge.project',
                        current_setting(
                            'app.knowledge_write_scope_type',
                            true
                        ),
                        current_setting(
                            'app.knowledge_write_scope_id',
                            true
                        )
                    )
                    OR public.knowledge_rls_has_permission(
                        'knowledge.manage_acl',
                        current_setting(
                            'app.knowledge_write_scope_type',
                            true
                        ),
                        current_setting(
                            'app.knowledge_write_scope_id',
                            true
                        )
                    )
                )
        $function$
        """
    )
    op.execute(
        """
        CREATE OR REPLACE FUNCTION public.knowledge_rls_can_access_label(
            requested_label_id text
        )
        RETURNS boolean
        LANGUAGE sql
        STABLE
        SECURITY DEFINER
        SET search_path = pg_catalog, pg_temp
        SET row_security = off
        AS $function$
            SELECT EXISTS (
                SELECT 1
                FROM public.knowledge_resources AS resource
                JOIN public.knowledge_security_labels AS label
                  ON label.security_label_id =
                     resource.security_label_id
                WHERE label.security_label_id = requested_label_id
                  AND resource.tenant_id = NULLIF(
                      current_setting('app.knowledge_tenant', true),
                      ''
                  )
                  AND (
                      public.knowledge_rls_has_permission(
                          'knowledge.read_all_scope',
                          resource.owner_scope_type,
                          resource.owner_scope_id
                      )
                      OR public.knowledge_rls_has_permission(
                          'knowledge.manage_acl',
                          resource.owner_scope_type,
                          resource.owner_scope_id
                      )
                      OR (
                          (
                              public.knowledge_rls_has_permission(
                                  'knowledge.read',
                                  resource.owner_scope_type,
                                  resource.owner_scope_id
                              )
                              OR public.knowledge_rls_has_permission(
                                  'knowledge.project',
                                  resource.owner_scope_type,
                                  resource.owner_scope_id
                              )
                          )
                          AND NULLIF(
                              current_setting(
                                  'app.knowledge_principals_json',
                                  true
                              ),
                              ''
                          ) IS NOT NULL
                          AND EXISTS (
                              SELECT 1
                              FROM
                                  public.knowledge_security_label_grants
                                      AS allowed
                              JOIN jsonb_to_recordset(
                                  current_setting(
                                      'app.knowledge_principals_json',
                                      true
                                  )::jsonb
                              ) AS principal(
                                  principal_type text,
                                  principal_id text
                              )
                                ON principal.principal_type =
                                   allowed.principal_type
                               AND principal.principal_id =
                                   allowed.principal_id
                              WHERE allowed.security_label_id =
                                    label.security_label_id
                                AND allowed.authz_revision =
                                    label.authz_revision
                                AND allowed.effect = 'allow'
                                AND (
                                    allowed.valid_from IS NULL
                                    OR allowed.valid_from <= NOW()
                                )
                                AND (
                                    allowed.valid_until IS NULL
                                    OR allowed.valid_until > NOW()
                                )
                          )
                          AND NOT EXISTS (
                              SELECT 1
                              FROM
                                  public.knowledge_security_label_grants
                                      AS denied
                              JOIN jsonb_to_recordset(
                                  current_setting(
                                      'app.knowledge_principals_json',
                                      true
                                  )::jsonb
                              ) AS principal(
                                  principal_type text,
                                  principal_id text
                              )
                                ON principal.principal_type =
                                   denied.principal_type
                               AND principal.principal_id =
                                   denied.principal_id
                              WHERE denied.security_label_id =
                                    label.security_label_id
                                AND denied.authz_revision =
                                    label.authz_revision
                                AND denied.effect = 'deny'
                                AND (
                                    denied.valid_from IS NULL
                                    OR denied.valid_from <= NOW()
                                )
                                AND (
                                    denied.valid_until IS NULL
                                    OR denied.valid_until > NOW()
                                )
                          )
                      )
                  )
                  AND (
                      NOT EXISTS (
                          SELECT 1
                          FROM public.knowledge_resource_agent_masks
                              AS any_mask
                          WHERE any_mask.knowledge_resource_id =
                                resource.knowledge_resource_id
                      )
                      OR NULLIF(
                          current_setting(
                              'app.knowledge_agent_role',
                              true
                          ),
                          ''
                      ) IS NULL
                      OR (
                          NOT EXISTS (
                              SELECT 1
                              FROM public.knowledge_resource_agent_masks
                                  AS denied_mask
                              WHERE denied_mask.knowledge_resource_id =
                                    resource.knowledge_resource_id
                                AND denied_mask.agent_role =
                                    current_setting(
                                        'app.knowledge_agent_role',
                                        true
                                    )
                                AND denied_mask.effect = 'deny'
                          )
                          AND (
                              NOT EXISTS (
                                  SELECT 1
                                  FROM public.knowledge_resource_agent_masks
                                      AS any_allow
                                  WHERE any_allow.knowledge_resource_id =
                                        resource.knowledge_resource_id
                                    AND any_allow.effect = 'allow'
                              )
                              OR EXISTS (
                                  SELECT 1
                                  FROM public.knowledge_resource_agent_masks
                                      AS allowed_mask
                                  WHERE allowed_mask.knowledge_resource_id =
                                        resource.knowledge_resource_id
                                    AND allowed_mask.agent_role =
                                        current_setting(
                                            'app.knowledge_agent_role',
                                            true
                                        )
                                    AND allowed_mask.effect = 'allow'
                              )
                          )
                      )
                  )
            )
        $function$
        """
    )
    op.execute(
        """
        CREATE OR REPLACE FUNCTION public.knowledge_rls_can_manage_label(
            requested_label_id text
        )
        RETURNS boolean
        LANGUAGE sql
        STABLE
        SECURITY DEFINER
        SET search_path = pg_catalog, pg_temp
        SET row_security = off
        AS $function$
            SELECT EXISTS (
                SELECT 1
                FROM public.knowledge_resources AS resource
                WHERE resource.security_label_id = requested_label_id
                  AND resource.tenant_id = NULLIF(
                      current_setting('app.knowledge_tenant', true),
                      ''
                  )
                  AND (
                      public.knowledge_rls_has_permission(
                          'knowledge.manage_acl',
                          resource.owner_scope_type,
                          resource.owner_scope_id
                      )
                      OR (
                          public.knowledge_rls_has_permission(
                              'knowledge.project',
                              resource.owner_scope_type,
                              resource.owner_scope_id
                          )
                          AND public.knowledge_rls_can_access_label(
                              requested_label_id
                          )
                      )
                  )
            )
        $function$
        """
    )
    op.execute(
        """
        CREATE OR REPLACE FUNCTION public.knowledge_rls_label_for_resource(
            requested_resource_id text
        )
        RETURNS text
        LANGUAGE sql
        STABLE
        SECURITY DEFINER
        SET search_path = pg_catalog, pg_temp
        SET row_security = off
        AS $function$
            SELECT resource.security_label_id
            FROM public.knowledge_resources AS resource
            WHERE resource.knowledge_resource_id = requested_resource_id
        $function$
        """
    )
    op.execute(
        """
        CREATE OR REPLACE FUNCTION public.knowledge_rls_label_for_projection(
            requested_projection_id text
        )
        RETURNS text
        LANGUAGE sql
        STABLE
        SECURITY DEFINER
        SET search_path = pg_catalog, pg_temp
        SET row_security = off
        AS $function$
            SELECT resource.security_label_id
            FROM public.knowledge_resource_projections AS projection
            JOIN public.knowledge_resources AS resource
              ON resource.knowledge_resource_id =
                 projection.knowledge_resource_id
            WHERE projection.projection_revision_id =
                  requested_projection_id
        $function$
        """
    )
    op.execute(
        """
        CREATE OR REPLACE FUNCTION public.knowledge_rls_label_for_record(
            requested_record_id text
        )
        RETURNS text
        LANGUAGE sql
        STABLE
        SECURITY DEFINER
        SET search_path = pg_catalog, pg_temp
        SET row_security = off
        AS $function$
            SELECT resource.security_label_id
            FROM public.knowledge_projection_records AS record
            JOIN public.knowledge_resources AS resource
              ON resource.knowledge_resource_id =
                 record.knowledge_resource_id
            WHERE record.projection_record_id = requested_record_id
        $function$
        """
    )
    op.execute(
        """
        CREATE OR REPLACE FUNCTION public.knowledge_rls_label_for_evidence(
            requested_evidence_id text
        )
        RETURNS text
        LANGUAGE sql
        STABLE
        SECURITY DEFINER
        SET search_path = pg_catalog, pg_temp
        SET row_security = off
        AS $function$
            SELECT evidence.security_label_id
            FROM public.knowledge_evidence_units AS evidence
            WHERE evidence.evidence_unit_row_id = requested_evidence_id
        $function$
        """
    )
    op.execute(
        """
        CREATE OR REPLACE FUNCTION public.knowledge_rls_label_for_community(
            requested_community_id text
        )
        RETURNS text
        LANGUAGE sql
        STABLE
        SECURITY DEFINER
        SET search_path = pg_catalog, pg_temp
        SET row_security = off
        AS $function$
            SELECT community.security_label_id
            FROM public.knowledge_graph_communities AS community
            WHERE community.community_id = requested_community_id
        $function$
        """
    )
    op.execute(
        """
        CREATE OR REPLACE FUNCTION public.knowledge_rls_can_access_entity(
            requested_entity_id text
        )
        RETURNS boolean
        LANGUAGE sql
        STABLE
        SECURITY DEFINER
        SET search_path = pg_catalog, pg_temp
        SET row_security = off
        AS $function$
            SELECT EXISTS (
                SELECT 1
                FROM public.knowledge_graph_mentions AS mention
                WHERE mention.entity_id = requested_entity_id
                  AND public.knowledge_rls_can_access_label(
                      mention.security_label_id
                  )
            )
        $function$
        """
    )
    op.execute(
        f"""
        REVOKE ALL ON FUNCTION
            public.knowledge_rls_has_permission(text, text, text),
            public.knowledge_rls_write_scope_allowed(),
            public.knowledge_rls_can_access_label(text),
            public.knowledge_rls_can_manage_label(text),
            public.knowledge_rls_label_for_resource(text),
            public.knowledge_rls_label_for_projection(text),
            public.knowledge_rls_label_for_record(text),
            public.knowledge_rls_label_for_evidence(text),
            public.knowledge_rls_label_for_community(text),
            public.knowledge_rls_can_access_entity(text)
        FROM PUBLIC;
        GRANT EXECUTE ON FUNCTION
            public.knowledge_rls_has_permission(text, text, text),
            public.knowledge_rls_write_scope_allowed(),
            public.knowledge_rls_can_access_label(text),
            public.knowledge_rls_can_manage_label(text),
            public.knowledge_rls_label_for_resource(text),
            public.knowledge_rls_label_for_projection(text),
            public.knowledge_rls_label_for_record(text),
            public.knowledge_rls_label_for_evidence(text),
            public.knowledge_rls_label_for_community(text),
            public.knowledge_rls_can_access_entity(text)
        TO {RUNTIME_ROLE};
        """
    )


def _policy(
    table: str,
    *,
    label_expression: str,
    check_expression: str | None = None,
) -> None:
    check = check_expression or (
        "public.knowledge_rls_can_manage_label("
        f"{label_expression}) "
        "OR ("
        "public.knowledge_rls_write_scope_allowed() "
        f"AND {label_expression} = current_setting("
        "'app.knowledge_write_security_label_id', true)"
        ")"
    )
    op.execute(
        f"""
        ALTER TABLE public.{table} ENABLE ROW LEVEL SECURITY;
        ALTER TABLE public.{table} FORCE ROW LEVEL SECURITY;
        CREATE POLICY knowledge_runtime_access
        ON public.{table}
        FOR ALL
        TO {RUNTIME_ROLE}
        USING (
            public.knowledge_rls_can_access_label({label_expression})
        )
        WITH CHECK ({check});
        """
    )


def _append_only_policy(
    table: str,
    *,
    label_expression: str,
    insert_check: str | None = None,
) -> None:
    check = insert_check or (
        "public.knowledge_rls_can_manage_label("
        f"{label_expression}) "
        "OR ("
        "public.knowledge_rls_write_scope_allowed() "
        f"AND {label_expression} = current_setting("
        "'app.knowledge_write_security_label_id', true)"
        ")"
    )
    op.execute(
        f"""
        ALTER TABLE public.{table} ENABLE ROW LEVEL SECURITY;
        ALTER TABLE public.{table} FORCE ROW LEVEL SECURITY;
        CREATE POLICY knowledge_runtime_select
        ON public.{table}
        FOR SELECT
        TO {RUNTIME_ROLE}
        USING (
            public.knowledge_rls_can_access_label({label_expression})
        );
        CREATE POLICY knowledge_runtime_insert
        ON public.{table}
        FOR INSERT
        TO {RUNTIME_ROLE}
        WITH CHECK ({check});
        """
    )


def _create_policies() -> None:
    _policy("external_docs", label_expression="security_label_id")
    _append_only_policy(
        "knowledge_acl_audit_log",
        label_expression="security_label_id",
    )
    _append_only_policy(
        "knowledge_agent_mask_audit_log",
        label_expression=(
            "public.knowledge_rls_label_for_resource("
            "knowledge_resource_id)"
        ),
    )
    _policy(
        "knowledge_embedding_channel_receipts",
        label_expression=(
            "public.knowledge_rls_label_for_evidence("
            "evidence_unit_row_id)"
        ),
    )
    _policy("knowledge_evidence_units", label_expression="security_label_id")
    _policy(
        "knowledge_graph_communities",
        label_expression="security_label_id",
    )
    _policy(
        "knowledge_graph_community_memberships",
        label_expression=(
            "public.knowledge_rls_label_for_community(community_id)"
        ),
    )
    _policy(
        "knowledge_graph_community_reports",
        label_expression=(
            "public.knowledge_rls_label_for_community(community_id)"
        ),
    )
    op.execute(
        f"""
        ALTER TABLE public.knowledge_graph_entities
            ENABLE ROW LEVEL SECURITY;
        ALTER TABLE public.knowledge_graph_entities
            FORCE ROW LEVEL SECURITY;
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
        """
    )
    _policy("knowledge_graph_mentions", label_expression="security_label_id")
    _policy(
        "knowledge_graph_relations",
        label_expression=(
            "public.knowledge_rls_label_for_projection("
            "projection_revision_id)"
        ),
    )
    _policy(
        "knowledge_projection_facets",
        label_expression=(
            "public.knowledge_rls_label_for_record(projection_record_id)"
        ),
    )
    _policy(
        "knowledge_projection_records",
        label_expression=(
            "public.knowledge_rls_label_for_resource("
            "knowledge_resource_id)"
        ),
    )
    _policy(
        "knowledge_resource_agent_masks",
        label_expression=(
            "public.knowledge_rls_label_for_resource("
            "knowledge_resource_id)"
        ),
    )
    _policy(
        "knowledge_resource_projections",
        label_expression=(
            "public.knowledge_rls_label_for_resource("
            "knowledge_resource_id)"
        ),
    )
    _policy("knowledge_resources", label_expression="security_label_id")
    _policy(
        "knowledge_security_label_grants",
        label_expression="security_label_id",
    )
    _policy(
        "knowledge_security_labels",
        label_expression="security_label_id",
    )


def upgrade() -> None:
    _create_role_and_privileges()
    _create_context_functions()
    _create_policies()


def downgrade() -> None:
    for table in reversed(RLS_TABLES):
        op.execute(
            f"""
            DROP POLICY IF EXISTS knowledge_runtime_access
                ON public.{table};
            DROP POLICY IF EXISTS knowledge_runtime_select
                ON public.{table};
            DROP POLICY IF EXISTS knowledge_runtime_insert
                ON public.{table};
            ALTER TABLE public.{table} NO FORCE ROW LEVEL SECURITY;
            ALTER TABLE public.{table} DISABLE ROW LEVEL SECURITY;
            """
        )
    op.execute(
        """
        DROP FUNCTION IF EXISTS
            public.knowledge_rls_can_access_entity(text);
        DROP FUNCTION IF EXISTS
            public.knowledge_rls_label_for_community(text);
        DROP FUNCTION IF EXISTS
            public.knowledge_rls_label_for_evidence(text);
        DROP FUNCTION IF EXISTS
            public.knowledge_rls_label_for_record(text);
        DROP FUNCTION IF EXISTS
            public.knowledge_rls_label_for_projection(text);
        DROP FUNCTION IF EXISTS
            public.knowledge_rls_label_for_resource(text);
        DROP FUNCTION IF EXISTS
            public.knowledge_rls_can_manage_label(text);
        DROP FUNCTION IF EXISTS
            public.knowledge_rls_can_access_label(text);
        DROP FUNCTION IF EXISTS
            public.knowledge_rls_write_scope_allowed();
        DROP FUNCTION IF EXISTS
            public.knowledge_rls_has_permission(text, text, text);
        """
    )
    for table in (*FULL_DML_TABLES, *APPEND_ONLY_TABLES):
        op.execute(
            f"""
            DO $revoke$
            BEGIN
                IF to_regclass('public.{table}') IS NOT NULL THEN
                    REVOKE ALL ON TABLE public.{table}
                    FROM {RUNTIME_ROLE};
                END IF;
            END
            $revoke$;
            """
        )
    op.execute(
        f"""
        REVOKE ALL ON ALL SEQUENCES IN SCHEMA public
            FROM {RUNTIME_ROLE};
        REVOKE USAGE ON SCHEMA public FROM {RUNTIME_ROLE};
        ALTER ROLE {RUNTIME_ROLE} NOLOGIN;
        """
    )
