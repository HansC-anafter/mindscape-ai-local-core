"""The only SQL owner for knowledge resources, labels, grants, and ACL audit."""

from __future__ import annotations

import hashlib
import json
from typing import Any, Iterable

from .contracts import PrincipalRef, RetrievalAccessContext
from .identity import (
    acl_mutation_id,
    knowledge_resource_id,
    security_grant_id,
    security_label_id,
)
from .write_contracts import (
    KnowledgeAclMutation,
    KnowledgeGrant,
    KnowledgeResourceBinding,
    KnowledgeResourceIdentity,
)


def _canonical_grants(grants: Iterable[KnowledgeGrant]) -> list[dict[str, Any]]:
    return [
        {
            "principal_type": grant.principal.type,
            "principal_id": grant.principal.id,
            "relation": grant.relation,
            "effect": grant.effect,
            "valid_from": (
                grant.valid_from.isoformat() if grant.valid_from else None
            ),
            "valid_until": (
                grant.valid_until.isoformat() if grant.valid_until else None
            ),
        }
        for grant in grants
    ]


def _diff_payload(
    *,
    event: str,
    grants: Iterable[KnowledgeGrant],
) -> tuple[dict[str, Any], str]:
    payload = {"event": event, "grants": _canonical_grants(grants)}
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return payload, hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def visibility_partition_hash_for_grants(
    grants: Iterable[KnowledgeGrant],
) -> str:
    """Hash normalized policy semantics, never the resource-specific label id."""

    encoded = json.dumps(
        _canonical_grants(grants),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


class KnowledgeAuthorizationConflictError(RuntimeError):
    """The resource or ACL revision changed before this writer committed."""


class KnowledgeAuthorizationStore:
    """Execute ACL mutations under the transaction owned by the caller."""

    def replace_existing_resource_grants(
        self,
        cursor: Any,
        *,
        knowledge_resource_id: str,
        tenant_id: str,
        scope_type: str,
        scope_id: str,
        access_context: RetrievalAccessContext,
        mutation: KnowledgeAclMutation,
    ) -> KnowledgeResourceBinding:
        """CAS-replace one existing label without owning the transaction."""

        cursor.execute(
            """
            SELECT
                resource.security_label_id,
                label.authz_revision
            FROM knowledge_resources AS resource
            JOIN knowledge_security_labels AS label
              ON label.security_label_id = resource.security_label_id
            WHERE resource.knowledge_resource_id = %s
              AND resource.tenant_id = %s
              AND resource.owner_scope_type = %s
              AND resource.owner_scope_id = %s
            FOR UPDATE OF resource, label
            """,
            (
                knowledge_resource_id,
                tenant_id,
                scope_type,
                scope_id,
            ),
        )
        row = cursor.fetchone()
        if row is None:
            raise LookupError("knowledge_resource_not_found")
        label_id = str(row[0])
        revision = self._replace_grants(
            cursor,
            resource_id=knowledge_resource_id,
            label_id=label_id,
            current_revision=int(row[1]),
            access_context=access_context,
            mutation=mutation,
        )
        return KnowledgeResourceBinding(
            knowledge_resource_id=knowledge_resource_id,
            security_label_id=label_id,
            authz_revision=revision,
            visibility_partition_hash=visibility_partition_hash_for_grants(
                mutation.grants
            ),
            created=False,
        )

    def ensure_resource(
        self,
        cursor: Any,
        *,
        identity: KnowledgeResourceIdentity,
        access_context: RetrievalAccessContext,
        acl_mutation: KnowledgeAclMutation | None = None,
        initial_grants: Iterable[KnowledgeGrant] = (),
    ) -> KnowledgeResourceBinding:
        resource_id = knowledge_resource_id(
            owner_capability_code=identity.owner_capability_code,
            source_kind=identity.source_kind,
            source_ref=identity.source_ref,
            owner_scope_type=identity.owner_scope_type,
            owner_scope_id=identity.owner_scope_id,
        )
        label_id = security_label_id(resource_id)
        cursor.execute(
            """
            SELECT
                resource.knowledge_resource_id,
                resource.security_label_id,
                label.authz_revision
            FROM knowledge_resources AS resource
            JOIN knowledge_security_labels AS label
              ON label.security_label_id = resource.security_label_id
            WHERE resource.tenant_id = %s
              AND resource.owner_capability_code = %s
              AND resource.source_kind = %s
              AND resource.source_ref = %s
              AND resource.owner_scope_type = %s
              AND resource.owner_scope_id = %s
            FOR UPDATE OF resource, label
            """,
            (
                identity.tenant_id,
                identity.owner_capability_code,
                identity.source_kind,
                identity.source_ref,
                identity.owner_scope_type,
                identity.owner_scope_id,
            ),
        )
        existing = cursor.fetchone()
        created = existing is None
        if created:
            self._create_resource(
                cursor,
                identity=identity,
                access_context=access_context,
                resource_id=resource_id,
                label_id=label_id,
                initial_grants=initial_grants,
            )
            current_revision = 1
        else:
            if str(existing[0]) != resource_id or str(existing[1]) != label_id:
                raise KnowledgeAuthorizationConflictError(
                    "knowledge_resource_stable_identity_mismatch"
                )
            current_revision = int(existing[2])
            cursor.execute(
                """
                UPDATE knowledge_resources
                SET source_app = %s,
                    source_id = %s,
                    source_revision = %s,
                    active = TRUE,
                    deleted_at = NULL,
                    updated_at = NOW()
                WHERE knowledge_resource_id = %s
                """,
                (
                    identity.source_app,
                    identity.source_id,
                    identity.source_revision,
                    resource_id,
                ),
            )

        if acl_mutation is not None:
            current_revision = self._replace_grants(
                cursor,
                resource_id=resource_id,
                label_id=label_id,
                current_revision=current_revision,
                access_context=access_context,
                mutation=acl_mutation,
            )
        cursor.execute(
            """
            SELECT
                principal_type, principal_id, relation, effect,
                valid_from, valid_until
            FROM knowledge_security_label_grants
            WHERE security_label_id = %s
              AND authz_revision = %s
            ORDER BY
                principal_type, principal_id, relation, effect,
                valid_from NULLS FIRST, valid_until NULLS FIRST
            """,
            (label_id, current_revision),
        )
        current_grants = tuple(
            KnowledgeGrant(
                principal=PrincipalRef(str(row[0]), str(row[1])),
                relation=str(row[2]),
                effect=str(row[3]),
                valid_from=row[4],
                valid_until=row[5],
            )
            for row in cursor.fetchall()
        )
        if not current_grants:
            raise KnowledgeAuthorizationConflictError(
                "knowledge_resource_current_grants_missing"
            )

        return KnowledgeResourceBinding(
            knowledge_resource_id=resource_id,
            security_label_id=label_id,
            authz_revision=current_revision,
            visibility_partition_hash=visibility_partition_hash_for_grants(
                current_grants
            ),
            created=created,
        )

    def _create_resource(
        self,
        cursor: Any,
        *,
        identity: KnowledgeResourceIdentity,
        access_context: RetrievalAccessContext,
        resource_id: str,
        label_id: str,
        initial_grants: Iterable[KnowledgeGrant] = (),
    ) -> None:
        owner_grant = KnowledgeGrant(
            principal=PrincipalRef("user", access_context.subject_user_id),
            relation="owner",
        )
        grants = tuple(
            sorted(
                {owner_grant, *tuple(initial_grants)},
                key=lambda grant: (
                    grant.principal.type,
                    grant.principal.id,
                    grant.relation,
                    grant.effect,
                ),
            )
        )
        cursor.execute(
            """
            INSERT INTO knowledge_security_labels (
                security_label_id, classification, authz_revision
            ) VALUES (%s, %s, 1)
            """,
            (label_id, identity.classification),
        )
        cursor.execute(
            """
            INSERT INTO knowledge_resources (
                knowledge_resource_id, tenant_id, owner_capability_code,
                source_kind, source_app, source_id, source_ref,
                source_revision, owner_scope_type, owner_scope_id,
                security_label_id
            ) VALUES (
                %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s
            )
            """,
            (
                resource_id,
                identity.tenant_id,
                identity.owner_capability_code,
                identity.source_kind,
                identity.source_app,
                identity.source_id,
                identity.source_ref,
                identity.source_revision,
                identity.owner_scope_type,
                identity.owner_scope_id,
                label_id,
            ),
        )
        self._insert_grants(
            cursor,
            label_id=label_id,
            grants=grants,
            authz_revision=1,
        )
        self._insert_audit(
            cursor,
            resource_id=resource_id,
            label_id=label_id,
            old_revision=0,
            new_revision=1,
            access_context=access_context,
            event="resource_created",
            grants=grants,
        )

    def _replace_grants(
        self,
        cursor: Any,
        *,
        resource_id: str,
        label_id: str,
        current_revision: int,
        access_context: RetrievalAccessContext,
        mutation: KnowledgeAclMutation,
    ) -> int:
        if mutation.expected_authz_revision != current_revision:
            raise KnowledgeAuthorizationConflictError(
                "knowledge_acl_expected_revision_conflict"
            )
        new_revision = current_revision + 1
        cursor.execute(
            """
            UPDATE knowledge_security_labels
            SET authz_revision = %s, updated_at = NOW()
            WHERE security_label_id = %s
              AND authz_revision = %s
            RETURNING authz_revision
            """,
            (new_revision, label_id, current_revision),
        )
        updated = cursor.fetchone()
        if updated is None or int(updated[0]) != new_revision:
            raise KnowledgeAuthorizationConflictError(
                "knowledge_acl_compare_and_swap_failed"
            )
        cursor.execute(
            "DELETE FROM knowledge_security_label_grants "
            "WHERE security_label_id = %s",
            (label_id,),
        )
        self._insert_grants(
            cursor,
            label_id=label_id,
            grants=mutation.grants,
            authz_revision=new_revision,
        )
        self._insert_audit(
            cursor,
            resource_id=resource_id,
            label_id=label_id,
            old_revision=current_revision,
            new_revision=new_revision,
            access_context=access_context,
            event="grants_replaced",
            grants=mutation.grants,
        )
        return new_revision

    @staticmethod
    def _insert_grants(
        cursor: Any,
        *,
        label_id: str,
        grants: tuple[KnowledgeGrant, ...],
        authz_revision: int,
    ) -> None:
        cursor.executemany(
            """
            INSERT INTO knowledge_security_label_grants (
                grant_id, security_label_id, principal_type, principal_id,
                relation, effect, valid_from, valid_until, authz_revision
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            [
                (
                    security_grant_id(
                        label_id=label_id,
                        principal_type=grant.principal.type,
                        principal_id=grant.principal.id,
                        relation=grant.relation,
                        effect=grant.effect,
                    ),
                    label_id,
                    grant.principal.type,
                    grant.principal.id,
                    grant.relation,
                    grant.effect,
                    grant.valid_from,
                    grant.valid_until,
                    authz_revision,
                )
                for grant in grants
            ],
        )

    @staticmethod
    def _insert_audit(
        cursor: Any,
        *,
        resource_id: str,
        label_id: str,
        old_revision: int,
        new_revision: int,
        access_context: RetrievalAccessContext,
        event: str,
        grants: tuple[KnowledgeGrant, ...],
    ) -> None:
        payload, diff_digest = _diff_payload(event=event, grants=grants)
        mutation_id = acl_mutation_id(
            resource_id=resource_id,
            authz_revision=new_revision,
            diff_digest=diff_digest,
        )
        cursor.execute(
            """
            INSERT INTO knowledge_acl_audit_log (
                mutation_id, actor_user_id, principal_context_hash,
                knowledge_resource_id, security_label_id,
                old_authz_revision, new_authz_revision,
                diff_digest, normalized_diff
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb)
            """,
            (
                mutation_id,
                access_context.subject_user_id,
                access_context.principal_set_hash,
                resource_id,
                label_id,
                old_revision,
                new_revision,
                diff_digest,
                json.dumps(payload, sort_keys=True, separators=(",", ":")),
            ),
        )


__all__ = [
    "KnowledgeAuthorizationConflictError",
    "KnowledgeAuthorizationStore",
    "visibility_partition_hash_for_grants",
]
