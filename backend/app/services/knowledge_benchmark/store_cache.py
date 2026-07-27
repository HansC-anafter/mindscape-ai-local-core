"""Cache identity, final-hit receipt, and run-ledger SQL leaf."""

from __future__ import annotations

from time import time
from typing import Any, Iterable

from psycopg2.extras import Json, RealDictCursor

from backend.app.services.knowledge_authorization import (
    RetrievalAccessContext,
    set_local_knowledge_context,
)

from .store_common import sha256_json, stable_id


class KnowledgeBenchmarkCacheStoreMixin:
    def load_execution_seed(
        self,
        *,
        context: RetrievalAccessContext,
        group_id: str,
        catalog_id: str,
        catalog_revision: str,
        question_id: str,
        topology_revision: str,
        authorization_generation: str,
    ) -> dict[str, Any]:
        connection = self._connection_factory()
        try:
            cursor = connection.cursor(cursor_factory=RealDictCursor)
            set_local_knowledge_context(cursor, context)
            cursor.execute(
                """
                SELECT
                    question.*, catalog.catalog_id,
                    catalog.catalog_revision
                FROM knowledge_benchmark_questions AS question
                JOIN knowledge_benchmark_catalogs AS catalog
                  ON catalog.catalog_revision_id =
                     question.catalog_revision_id
                WHERE catalog.tenant_id = %s
                  AND catalog.owner_scope_type = 'group'
                  AND catalog.owner_scope_id = %s
                  AND catalog.catalog_id = %s
                  AND catalog.catalog_revision = %s
                  AND question.question_id = %s
                """,
                (
                    context.tenant_id,
                    group_id,
                    catalog_id,
                    catalog_revision,
                    question_id,
                ),
            )
            question = cursor.fetchone()
            if question is None:
                raise LookupError("knowledge_benchmark_question_not_found")
            cursor.execute(
                """
                SELECT
                    projection.projection_revision_id,
                    projection.projection_hash,
                    resource.knowledge_resource_id,
                    label.authz_revision,
                    projection.status
                FROM knowledge_resource_projections AS projection
                JOIN knowledge_resources AS resource
                  ON resource.knowledge_resource_id =
                     projection.knowledge_resource_id
                JOIN knowledge_security_labels AS label
                  ON label.security_label_id = resource.security_label_id
                WHERE resource.tenant_id = %s
                  AND resource.owner_scope_type = 'group'
                  AND resource.owner_scope_id = %s
                  AND resource.active
                  AND projection.active
                ORDER BY
                    resource.knowledge_resource_id,
                    projection.projection_revision_id
                LIMIT 5000
                """,
                (context.tenant_id, group_id),
            )
            projection_digest = sha256_json(
                [dict(row) for row in cursor.fetchall()]
            )
            request_payload = dict(question["canonical_request"])
            request_digest = sha256_json(request_payload)
            cache_key = sha256_json(
                {
                    "question_row_id": question["question_row_id"],
                    "question_hash": question["question_hash"],
                    "request_digest": request_digest,
                    "principal_set_hash": context.principal_set_hash,
                    "scope": ["group", group_id],
                    "topology_revision": topology_revision,
                    "authorization_generation": (
                        authorization_generation
                    ),
                    "projection_digest": projection_digest,
                }
            )
            cursor.execute(
                """
                UPDATE knowledge_benchmark_cache_entries
                SET state = 'stale_projection',
                    invalidated_at = COALESCE(invalidated_at, NOW())
                WHERE question_row_id = %s
                  AND principal_set_hash = %s
                  AND request_digest = %s
                  AND topology_revision = %s
                  AND authorization_generation = %s
                  AND projection_digest <> %s
                  AND state = 'active'
                """,
                (
                    question["question_row_id"],
                    context.principal_set_hash,
                    request_digest,
                    topology_revision,
                    authorization_generation,
                    projection_digest,
                ),
            )
            cursor.execute(
                """
                SELECT *
                FROM knowledge_benchmark_cache_entries
                WHERE cache_key = %s
                  AND state = 'active'
                """,
                (cache_key,),
            )
            cached = cursor.fetchone()
            connection.commit()
            return {
                "question": dict(question),
                "request_digest": request_digest,
                "projection_digest": projection_digest,
                "cache_key": cache_key,
                "cached": dict(cached) if cached is not None else None,
            }
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def record_cache_hit(
        self,
        *,
        context: RetrievalAccessContext,
        seed: dict[str, Any],
        latency_ms: int,
    ) -> None:
        self._write_receipt(
            context=context,
            seed=seed,
            cache_status="hit",
            latency_ms=latency_ms,
            response_payload=dict(seed["cached"]["response_payload"]),
            update_cache="hit",
        )

    def record_stale_authorization(
        self,
        *,
        context: RetrievalAccessContext,
        seed: dict[str, Any],
        latency_ms: int,
    ) -> None:
        self._write_receipt(
            context=context,
            seed=seed,
            cache_status="stale_authorization",
            latency_ms=latency_ms,
            response_payload=dict(seed["cached"]["response_payload"]),
            update_cache="stale_authorization",
        )

    def store_miss(
        self,
        *,
        context: RetrievalAccessContext,
        seed: dict[str, Any],
        topology_revision: str,
        authorization_generation: str,
        response_payload: dict[str, Any],
        bindings: Iterable[tuple[str, int]],
        latency_ms: int,
    ) -> None:
        connection = self._connection_factory()
        try:
            cursor = connection.cursor()
            set_local_knowledge_context(cursor, context)
            binding_payload = [
                {
                    "knowledge_resource_id": resource_id,
                    "authz_revision": revision,
                }
                for resource_id, revision in sorted(set(bindings))
            ]
            question = seed["question"]
            cursor.execute(
                """
                INSERT INTO knowledge_benchmark_cache_entries (
                    cache_key, question_row_id, tenant_id,
                    owner_scope_type, owner_scope_id,
                    principal_set_hash, request_digest,
                    topology_revision, authorization_generation,
                    projection_digest, response_payload,
                    resource_bindings, state, hit_count
                ) VALUES (
                    %s, %s, %s, 'group', %s, %s, %s, %s, %s, %s,
                    %s::jsonb, %s::jsonb, 'active', 0
                )
                ON CONFLICT (cache_key) DO UPDATE
                SET response_payload = EXCLUDED.response_payload,
                    resource_bindings = EXCLUDED.resource_bindings,
                    state = 'active',
                    invalidated_at = NULL
                """,
                (
                    seed["cache_key"],
                    question["question_row_id"],
                    context.tenant_id,
                    question["owner_scope_id"],
                    context.principal_set_hash,
                    seed["request_digest"],
                    topology_revision,
                    authorization_generation,
                    seed["projection_digest"],
                    Json(response_payload),
                    Json(binding_payload),
                ),
            )
            self._insert_run(
                cursor,
                context=context,
                seed=seed,
                cache_status="miss",
                latency_ms=latency_ms,
                response_payload=response_payload,
            )
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def _write_receipt(
        self,
        *,
        context: RetrievalAccessContext,
        seed: dict[str, Any],
        cache_status: str,
        latency_ms: int,
        response_payload: dict[str, Any],
        update_cache: str,
    ) -> None:
        connection = self._connection_factory()
        try:
            cursor = connection.cursor()
            set_local_knowledge_context(cursor, context)
            if update_cache == "hit":
                cursor.execute(
                    """
                    UPDATE knowledge_benchmark_cache_entries
                    SET hit_count = hit_count + 1,
                        last_hit_at = NOW()
                    WHERE cache_key = %s
                      AND state = 'active'
                    """,
                    (seed["cache_key"],),
                )
            else:
                cursor.execute(
                    """
                    UPDATE knowledge_benchmark_cache_entries
                    SET state = 'stale_authorization',
                        invalidated_at = COALESCE(
                            invalidated_at,
                            NOW()
                        )
                    WHERE cache_key = %s
                    """,
                    (seed["cache_key"],),
                )
            self._insert_run(
                cursor,
                context=context,
                seed=seed,
                cache_status=cache_status,
                latency_ms=latency_ms,
                response_payload=response_payload,
            )
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    @staticmethod
    def _insert_run(
        cursor: Any,
        *,
        context: RetrievalAccessContext,
        seed: dict[str, Any],
        cache_status: str,
        latency_ms: int,
        response_payload: dict[str, Any],
    ) -> None:
        question = seed["question"]
        receipt = dict(response_payload.get("receipt") or {})
        cursor.execute(
            """
            INSERT INTO knowledge_benchmark_runs (
                run_id, question_row_id, cache_key, tenant_id,
                owner_scope_type, owner_scope_id,
                principal_set_hash, cache_status, request_digest,
                projection_digest, authorization_receipt_digest,
                latency_ms, evidence_count
            ) VALUES (
                %s, %s, %s, %s, 'group', %s, %s, %s, %s, %s,
                %s, %s, %s
            )
            """,
            (
                stable_id(
                    "kbr",
                    seed["cache_key"],
                    cache_status,
                    str(time()),
                ),
                question["question_row_id"],
                seed["cache_key"],
                context.tenant_id,
                question["owner_scope_id"],
                context.principal_set_hash,
                cache_status,
                seed["request_digest"],
                seed["projection_digest"],
                receipt.get("authorization_receipt_digest"),
                max(0, int(latency_ms)),
                len(response_payload.get("evidence") or ()),
            ),
        )


__all__ = ["KnowledgeBenchmarkCacheStoreMixin"]
