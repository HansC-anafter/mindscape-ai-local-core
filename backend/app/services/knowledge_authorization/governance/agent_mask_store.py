"""Caller-transaction leaf for agent narrowing-mask replacement."""

from __future__ import annotations

import hashlib
import json
from typing import Any, Iterable

from ..contracts import RetrievalAccessContext


def _canonical(
    masks: Iterable[tuple[str, str]],
) -> tuple[tuple[str, str], ...]:
    return tuple(sorted(set(masks)))


def _digest(value: Any) -> str:
    encoded = json.dumps(
        value,
        ensure_ascii=True,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


class KnowledgeAgentMaskStore:
    """Agent roles only narrow; this store never creates human grants."""

    @staticmethod
    def replace(
        cursor: Any,
        *,
        resource_id: str,
        authz_revision: int,
        masks: Iterable[tuple[str, str]],
        context: RetrievalAccessContext,
    ) -> str:
        normalized = _canonical(masks)
        cursor.execute(
            """
            SELECT policy_revision
            FROM knowledge_resource_agent_masks
            WHERE knowledge_resource_id = %s
            ORDER BY policy_revision
            LIMIT 1
            """,
            (resource_id,),
        )
        old_row = cursor.fetchone()
        old_revision = str(old_row[0]) if old_row is not None else None
        policy_revision = _digest(
            {
                "knowledge_resource_id": resource_id,
                "authz_revision": authz_revision,
                "masks": normalized,
            }
        )
        cursor.execute(
            """
            DELETE FROM knowledge_resource_agent_masks
            WHERE knowledge_resource_id = %s
            """,
            (resource_id,),
        )
        if normalized:
            cursor.executemany(
                """
                INSERT INTO knowledge_resource_agent_masks (
                    mask_id, knowledge_resource_id, agent_role,
                    effect, policy_revision
                ) VALUES (%s, %s, %s, %s, %s)
                """,
                [
                    (
                        _digest(
                            {
                                "resource_id": resource_id,
                                "role": role,
                                "effect": effect,
                            }
                        ),
                        resource_id,
                        role,
                        effect,
                        policy_revision,
                    )
                    for role, effect in normalized
                ],
            )
        mutation_id = _digest(
            {
                "resource_id": resource_id,
                "policy_revision": policy_revision,
                "actor_user_id": context.subject_user_id,
            }
        )
        cursor.execute(
            """
            INSERT INTO knowledge_agent_mask_audit_log (
                mutation_id, knowledge_resource_id, actor_user_id,
                principal_context_hash, old_policy_revision,
                new_policy_revision, normalized_masks
            ) VALUES (%s, %s, %s, %s, %s, %s, %s::jsonb)
            ON CONFLICT (mutation_id) DO NOTHING
            """,
            (
                mutation_id,
                resource_id,
                context.subject_user_id,
                context.principal_set_hash,
                old_revision,
                policy_revision,
                json.dumps(
                    [
                        {"agent_role": role, "effect": effect}
                        for role, effect in normalized
                    ],
                    separators=(",", ":"),
                    sort_keys=True,
                ),
            ),
        )
        return policy_revision


__all__ = ["KnowledgeAgentMaskStore"]
