"""Transaction-local PostgreSQL context for knowledge RLS and SQL leaves."""

from __future__ import annotations

import json
from typing import Any

from .contracts import RetrievalAccessContext


def principals_json(context: RetrievalAccessContext) -> str:
    return json.dumps(
        [
            {"principal_type": item.type, "principal_id": item.id}
            for item in context.principals
        ],
        sort_keys=True,
        separators=(",", ":"),
    )


def permissions_json(context: RetrievalAccessContext) -> str:
    return json.dumps(
        [permission.as_dict() for permission in context.permissions],
        sort_keys=True,
        separators=(",", ":"),
    )


def set_local_knowledge_context(
    cursor: Any,
    context: RetrievalAccessContext,
    *,
    write_scope_type: str | None = None,
    write_scope_id: str | None = None,
    write_resource_id: str | None = None,
    write_security_label_id: str | None = None,
) -> None:
    """Set only transaction-local values; pooled sessions retain no identity."""

    if (write_scope_type is None) != (write_scope_id is None):
        raise ValueError("knowledge_rls_write_scope_incomplete")
    write_identity = (write_resource_id, write_security_label_id)
    if any(value is not None for value in write_identity) and (
        write_scope_type is None or not all(write_identity)
    ):
        raise ValueError("knowledge_rls_write_identity_incomplete")
    membership_revision = "|".join(
        membership.revision for membership in context.memberships
    )
    cursor.execute(
        """
        SELECT
            set_config('app.knowledge_subject', %s, TRUE),
            set_config('app.knowledge_tenant', %s, TRUE),
            set_config('app.knowledge_principals_json', %s, TRUE),
            set_config('app.knowledge_permissions_json', %s, TRUE),
            set_config('app.knowledge_scope_hash', %s, TRUE),
            set_config('app.knowledge_context_revision', %s, TRUE),
            set_config('app.knowledge_agent_role', %s, TRUE),
            set_config('app.knowledge_write_scope_type', %s, TRUE),
            set_config('app.knowledge_write_scope_id', %s, TRUE),
            set_config('app.knowledge_write_resource_id', %s, TRUE),
            set_config('app.knowledge_write_security_label_id', %s, TRUE)
        """,
        (
            context.subject_user_id,
            context.tenant_id,
            principals_json(context),
            permissions_json(context),
            context.principal_set_hash,
            membership_revision or "direct-user",
            context.agent_mask.role if context.agent_mask else "",
            write_scope_type or "",
            write_scope_id or "",
            write_resource_id or "",
            write_security_label_id or "",
        ),
    )


__all__ = [
    "permissions_json",
    "principals_json",
    "set_local_knowledge_context",
]
