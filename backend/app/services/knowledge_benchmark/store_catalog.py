"""Catalog registration and bounded stats SQL leaf."""

from __future__ import annotations

from typing import Any

from psycopg2.extras import Json, RealDictCursor

from backend.app.services.knowledge_authorization import (
    RetrievalAccessContext,
    set_local_knowledge_context,
)

from .contracts import BenchmarkCatalogCommand
from .store_common import sha256_json, stable_id


class KnowledgeBenchmarkCatalogStoreMixin:
    def register_catalog(
        self,
        *,
        context: RetrievalAccessContext,
        command: BenchmarkCatalogCommand,
    ) -> dict[str, Any]:
        if not context.has_permission(
            "knowledge.project",
            scope_type="group",
            scope_id=command.group_id,
        ):
            raise PermissionError("knowledge_benchmark_project_required")
        question_payloads = [
            item.model_dump(mode="json")
            for item in sorted(
                command.questions,
                key=lambda question: question.ordinal,
            )
        ]
        content_hash = sha256_json(question_payloads)
        catalog_revision_id = stable_id(
            "kbc",
            context.tenant_id,
            command.group_id,
            command.catalog_id,
            command.catalog_revision,
        )
        connection = self._connection_factory()
        try:
            cursor = connection.cursor(cursor_factory=RealDictCursor)
            set_local_knowledge_context(cursor, context)
            cursor.execute(
                """
                SELECT content_hash, question_count
                FROM knowledge_benchmark_catalogs
                WHERE catalog_revision_id = %s
                """,
                (catalog_revision_id,),
            )
            existing = cursor.fetchone()
            if existing is not None:
                if (
                    str(existing["content_hash"]) != content_hash
                    or int(existing["question_count"])
                    != len(question_payloads)
                ):
                    raise ValueError(
                        "knowledge_benchmark_revision_hash_conflict"
                    )
                connection.commit()
                return {
                    "state": "reused",
                    "catalog_revision_id": catalog_revision_id,
                    "content_hash": content_hash,
                    "question_count": len(question_payloads),
                }
            cursor.execute(
                """
                UPDATE knowledge_benchmark_catalogs
                SET active = FALSE
                WHERE tenant_id = %s
                  AND owner_scope_type = 'group'
                  AND owner_scope_id = %s
                  AND catalog_id = %s
                  AND active
                """,
                (
                    context.tenant_id,
                    command.group_id,
                    command.catalog_id,
                ),
            )
            cursor.execute(
                """
                INSERT INTO knowledge_benchmark_catalogs (
                    catalog_revision_id, tenant_id, owner_scope_type,
                    owner_scope_id, catalog_id, catalog_revision,
                    dispatch_workspace_id, content_hash, question_count,
                    created_by_user_id, active
                ) VALUES (
                    %s, %s, 'group', %s, %s, %s, %s, %s, %s, %s, TRUE
                )
                """,
                (
                    catalog_revision_id,
                    context.tenant_id,
                    command.group_id,
                    command.catalog_id,
                    command.catalog_revision,
                    command.workspace_id,
                    content_hash,
                    len(question_payloads),
                    context.subject_user_id,
                ),
            )
            for payload in question_payloads:
                question_hash = sha256_json(payload)
                cursor.execute(
                    """
                    INSERT INTO knowledge_benchmark_questions (
                        question_row_id, catalog_revision_id, tenant_id,
                        owner_scope_type, owner_scope_id, question_id,
                        domain_id, tier, benchmark_class, question_text,
                        canonical_request, rubric, question_hash, ordinal
                    ) VALUES (
                        %s, %s, %s, 'group', %s, %s, %s, %s, %s, %s,
                        %s::jsonb, %s::jsonb, %s, %s
                    )
                    """,
                    (
                        stable_id(
                            "kbq",
                            catalog_revision_id,
                            str(payload["question_id"]),
                        ),
                        catalog_revision_id,
                        context.tenant_id,
                        command.group_id,
                        payload["question_id"],
                        payload["domain_id"],
                        payload["tier"],
                        payload["benchmark_class"],
                        payload["question_text"],
                        Json(payload["canonical_request"]),
                        Json(payload["rubric"]),
                        question_hash,
                        payload["ordinal"],
                    ),
                )
            connection.commit()
            return {
                "state": "registered",
                "catalog_revision_id": catalog_revision_id,
                "content_hash": content_hash,
                "question_count": len(question_payloads),
            }
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def stats(
        self,
        *,
        context: RetrievalAccessContext,
        group_id: str,
        catalog_id: str,
        catalog_revision: str,
        limit: int,
    ) -> dict[str, Any]:
        connection = self._connection_factory()
        try:
            cursor = connection.cursor(cursor_factory=RealDictCursor)
            set_local_knowledge_context(cursor, context)
            cursor.execute(
                """
                SELECT
                    question.question_id,
                    question.domain_id,
                    question.tier,
                    run.cache_status,
                    COUNT(run.run_id)::integer AS run_count,
                    MAX(run.created_at) AS last_run_at
                FROM knowledge_benchmark_catalogs AS catalog
                JOIN knowledge_benchmark_questions AS question
                  ON question.catalog_revision_id =
                     catalog.catalog_revision_id
                LEFT JOIN knowledge_benchmark_runs AS run
                  ON run.question_row_id = question.question_row_id
                WHERE catalog.tenant_id = %s
                  AND catalog.owner_scope_type = 'group'
                  AND catalog.owner_scope_id = %s
                  AND catalog.catalog_id = %s
                  AND catalog.catalog_revision = %s
                GROUP BY
                    question.question_id,
                    question.domain_id,
                    question.tier,
                    run.cache_status,
                    question.ordinal
                ORDER BY question.ordinal, run.cache_status
                LIMIT %s
                """,
                (
                    context.tenant_id,
                    group_id,
                    catalog_id,
                    catalog_revision,
                    max(1, min(int(limit), 500)),
                ),
            )
            rows = [dict(row) for row in cursor.fetchall()]
            connection.commit()
            return {"rows": rows, "row_count": len(rows)}
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()


__all__ = ["KnowledgeBenchmarkCatalogStoreMixin"]
