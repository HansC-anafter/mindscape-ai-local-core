"""SQL statements for the bounded Dashboard PostgreSQL read plane."""

from sqlalchemy import text


SUMMARY_COUNTS_QUERY = text(
    """
    WITH authorized_workspaces AS (
        SELECT workspace_id, workspace_order
        FROM unnest(CAST(:workspace_ids AS text[])) WITH ORDINALITY
             AS authorized(workspace_id, workspace_order)
    ),
    execution_candidates AS MATERIALIZED (
        SELECT candidate.status
        FROM authorized_workspaces AS authorized
        CROSS JOIN LATERAL (
            SELECT execution.status
            FROM playbook_executions AS execution
            WHERE execution.workspace_id = authorized.workspace_id
            ORDER BY execution.created_at DESC, execution.id DESC
            LIMIT 50
        ) AS candidate
    ),
    pending_tasks AS (
        SELECT COUNT(*) AS count
        FROM tasks
        WHERE workspace_id = ANY(CAST(:workspace_ids AS text[]))
          AND status = 'pending'
    )
    SELECT
        pending_tasks.count AS open_assignments,
        COUNT(*) FILTER (WHERE execution_candidates.status = 'running') AS open_cases,
        COUNT(*) FILTER (
            WHERE execution_candidates.status IN ('paused', 'failed')
        ) AS blocked_cases,
        COUNT(*) FILTER (WHERE execution_candidates.status = 'running') AS running_jobs
    FROM pending_tasks
    LEFT JOIN execution_candidates ON TRUE
    GROUP BY pending_tasks.count
    """
)


INBOX_PAGE_QUERY = text(
    """
    WITH authorized_workspaces AS (
        SELECT workspace_id
        FROM unnest(CAST(:workspace_ids AS text[])) AS authorized(workspace_id)
    ),
    workspace_candidates AS MATERIALIZED (
        SELECT candidate.task_id, candidate.workspace_id, candidate.created_at
        FROM authorized_workspaces AS authorized
        CROSS JOIN LATERAL (
            SELECT
                source.id AS task_id,
                source.workspace_id,
                source.created_at
            FROM tasks AS source
            WHERE source.workspace_id = authorized.workspace_id
              AND source.status = 'pending'
            ORDER BY source.created_at DESC, source.id DESC
            LIMIT :candidate_limit
        ) AS candidate
    ),
    page_ids AS MATERIALIZED (
        SELECT task_id, workspace_id, created_at
        FROM workspace_candidates
        ORDER BY created_at DESC, task_id DESC
        LIMIT :limit OFFSET :offset
    )
    SELECT
        projection.task_id,
        projection.workspace_id,
        projection.execution_id,
        projection.pack_id,
        projection.task_type,
        source.status,
        COALESCE(
            source.params ->> 'description',
            projection.summary,
            ''
        ) AS description,
        projection.created_at,
        projection.started_at,
        projection.updated_at
    FROM page_ids
    JOIN tasks AS source ON source.id = page_ids.task_id
    JOIN task_summary_projection AS projection
      ON projection.task_id = page_ids.task_id
    ORDER BY page_ids.created_at DESC, page_ids.task_id DESC
    """
)


PENDING_TASK_COUNT_QUERY = text(
    """
    SELECT COUNT(*) AS count
    FROM tasks
    WHERE workspace_id = ANY(CAST(:workspace_ids AS text[]))
      AND status = 'pending'
    """
)


CASE_PAGE_QUERY = text(
    """
    WITH authorized_workspaces AS (
        SELECT workspace_id, workspace_order
        FROM unnest(CAST(:workspace_ids AS text[])) WITH ORDINALITY
             AS authorized(workspace_id, workspace_order)
    ),
    workspace_candidates AS MATERIALIZED (
        SELECT
            candidate.execution_id,
            candidate.workspace_id,
            candidate.status,
            candidate.created_at,
            candidate.updated_at,
            authorized.workspace_order
        FROM authorized_workspaces AS authorized
        CROSS JOIN LATERAL (
            SELECT
                execution.id AS execution_id,
                execution.workspace_id,
                execution.status,
                execution.created_at,
                execution.updated_at
            FROM playbook_executions AS execution
            WHERE execution.workspace_id = authorized.workspace_id
            ORDER BY execution.created_at DESC, execution.id DESC
            LIMIT 100
        ) AS candidate
    ),
    page_ids AS MATERIALIZED (
        SELECT
            execution_id,
            workspace_id,
            status,
            created_at,
            updated_at,
            workspace_order,
            COUNT(*) OVER () AS bounded_total
        FROM workspace_candidates
        ORDER BY
            CASE WHEN status IN ('paused', 'failed') THEN 0 ELSE 1 END,
            updated_at DESC NULLS LAST,
            workspace_order,
            execution_id DESC
        LIMIT :limit OFFSET :offset
    ),
    task_counts AS MATERIALIZED (
        SELECT source.execution_id, COUNT(*) AS count
        FROM tasks AS source
        JOIN page_ids
          ON page_ids.execution_id = source.execution_id
         AND page_ids.workspace_id = source.workspace_id
        GROUP BY source.execution_id
    )
    SELECT
        page_ids.bounded_total,
        page_ids.execution_id AS id,
        page_ids.workspace_id,
        workspace.title AS workspace_name,
        page_ids.status,
        execution.playbook_code,
        execution.metadata,
        page_ids.created_at,
        page_ids.updated_at,
        COALESCE(task_counts.count, 0) AS tasks_count
    FROM page_ids
    JOIN playbook_executions AS execution
      ON execution.id = page_ids.execution_id
    JOIN workspaces AS workspace
      ON workspace.id = page_ids.workspace_id
    LEFT JOIN task_counts
      ON task_counts.execution_id = page_ids.execution_id
    ORDER BY
        CASE WHEN page_ids.status IN ('paused', 'failed') THEN 0 ELSE 1 END,
        page_ids.updated_at DESC NULLS LAST,
        page_ids.workspace_order,
        page_ids.execution_id DESC
    """
)


CASE_BOUNDED_TOTAL_QUERY = text(
    """
    WITH authorized_workspaces AS (
        SELECT workspace_id
        FROM unnest(CAST(:workspace_ids AS text[])) AS authorized(workspace_id)
    ),
    workspace_candidates AS MATERIALIZED (
        SELECT candidate.execution_id
        FROM authorized_workspaces AS authorized
        CROSS JOIN LATERAL (
            SELECT execution.id AS execution_id
            FROM playbook_executions AS execution
            WHERE execution.workspace_id = authorized.workspace_id
            ORDER BY execution.created_at DESC, execution.id DESC
            LIMIT 100
        ) AS candidate
    )
    SELECT COUNT(*) AS count
    FROM workspace_candidates
    """
)


ASSIGNMENT_CANDIDATE_CTES = """
    WITH authorized_workspaces AS (
        SELECT workspace_id, workspace_order
        FROM unnest(CAST(:workspace_ids AS text[])) WITH ORDINALITY
             AS authorized(workspace_id, workspace_order)
    ),
    source_statuses AS (
        SELECT source_status
        FROM unnest(CAST(:source_statuses AS text[])) AS statuses(source_status)
    ),
    status_candidates AS MATERIALIZED (
        SELECT
            candidate.task_id,
            candidate.workspace_id,
            candidate.status,
            candidate.created_at,
            authorized.workspace_order
        FROM authorized_workspaces AS authorized
        CROSS JOIN source_statuses AS statuses
        CROSS JOIN LATERAL (
            SELECT
                source.id AS task_id,
                source.workspace_id,
                source.status,
                source.created_at
            FROM tasks AS source
            WHERE source.workspace_id = authorized.workspace_id
              AND source.status = statuses.source_status
            ORDER BY source.created_at DESC, source.id DESC
            LIMIT 100
        ) AS candidate
    ),
    workspace_candidates AS MATERIALIZED (
        SELECT task_id, workspace_id, status, created_at, workspace_order
        FROM (
            SELECT
                status_candidates.*,
                ROW_NUMBER() OVER (
                    PARTITION BY workspace_id
                    ORDER BY created_at DESC, task_id DESC
                ) AS workspace_rank
            FROM status_candidates
        ) AS ranked
        WHERE workspace_rank <= 100
    )
"""


ASSIGNMENT_PAGE_QUERY = text(
    ASSIGNMENT_CANDIDATE_CTES
    + """,
    page_ids AS MATERIALIZED (
        SELECT
            task_id,
            workspace_id,
            status,
            created_at,
            workspace_order,
            COUNT(*) OVER () AS bounded_total
        FROM workspace_candidates
        ORDER BY
            CASE WHEN status = 'pending' THEN 0 ELSE 1 END,
            created_at DESC,
            workspace_order,
            task_id DESC
        LIMIT :limit OFFSET :offset
    )
    SELECT
        page_ids.bounded_total,
        page_ids.task_id AS id,
        page_ids.workspace_id,
        workspace.title AS workspace_name,
        projection.execution_id,
        projection.pack_id,
        projection.task_type,
        page_ids.status,
        COALESCE(source.params ->> 'description', '') AS description,
        COALESCE(source.execution_context ->> 'playbook_code', '') AS case_title,
        page_ids.created_at,
        source.started_at,
        source.completed_at
    FROM page_ids
    JOIN tasks AS source ON source.id = page_ids.task_id
    JOIN task_summary_projection AS projection
      ON projection.task_id = page_ids.task_id
    JOIN workspaces AS workspace
      ON workspace.id = page_ids.workspace_id
    ORDER BY
        CASE WHEN page_ids.status = 'pending' THEN 0 ELSE 1 END,
        page_ids.created_at DESC,
        page_ids.workspace_order,
        page_ids.task_id DESC
    """
)


ASSIGNMENT_BOUNDED_TOTAL_QUERY = text(
    ASSIGNMENT_CANDIDATE_CTES
    + """
    SELECT COUNT(*) AS count
    FROM workspace_candidates
    """
)


WORKSPACE_PAGE_QUERY = text(
    """
    WITH page_workspaces AS MATERIALIZED (
        SELECT
            workspace.id,
            workspace.title,
            workspace.description,
            workspace.created_at,
            workspace.updated_at,
            COUNT(*) OVER () AS bounded_total
        FROM workspaces AS workspace
        WHERE workspace.id = ANY(CAST(:workspace_ids AS text[]))
          AND (
              CAST(:search AS text) IS NULL
              OR LOWER(COALESCE(workspace.title, '')) LIKE
                 '%' || LOWER(CAST(:search AS text)) || '%'
              OR LOWER(COALESCE(workspace.description, '')) LIKE
                 '%' || LOWER(CAST(:search AS text)) || '%'
          )
        ORDER BY workspace.updated_at DESC NULLS LAST, workspace.id
        LIMIT :limit OFFSET :offset
    ),
    execution_stats AS MATERIALIZED (
        SELECT
            page_workspaces.id AS workspace_id,
            COUNT(*) FILTER (WHERE recent_execution.status = 'running') AS open_cases
        FROM page_workspaces
        LEFT JOIN LATERAL (
            SELECT execution.status
            FROM playbook_executions AS execution
            WHERE execution.workspace_id = page_workspaces.id
            ORDER BY execution.created_at DESC, execution.id DESC
            LIMIT 100
        ) AS recent_execution ON TRUE
        GROUP BY page_workspaces.id
    )
    SELECT
        page_workspaces.bounded_total,
        page_workspaces.id,
        page_workspaces.title,
        page_workspaces.description,
        page_workspaces.created_at,
        page_workspaces.updated_at,
        COALESCE(execution_stats.open_cases, 0) AS open_cases
    FROM page_workspaces
    LEFT JOIN execution_stats
      ON execution_stats.workspace_id = page_workspaces.id
    ORDER BY page_workspaces.updated_at DESC NULLS LAST, page_workspaces.id
    """
)


WORKSPACE_BOUNDED_TOTAL_QUERY = text(
    """
    SELECT COUNT(*) AS count
    FROM workspaces AS workspace
    WHERE workspace.id = ANY(CAST(:workspace_ids AS text[]))
      AND (
          CAST(:search AS text) IS NULL
          OR LOWER(COALESCE(workspace.title, '')) LIKE
             '%' || LOWER(CAST(:search AS text)) || '%'
          OR LOWER(COALESCE(workspace.description, '')) LIKE
             '%' || LOWER(CAST(:search AS text)) || '%'
      )
    """
)
