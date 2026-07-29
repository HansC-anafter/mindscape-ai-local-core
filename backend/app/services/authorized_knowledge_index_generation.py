"""Generation transaction leaf for the authorized knowledge writer."""

from __future__ import annotations

from dataclasses import replace
from typing import Any, Optional

from backend.app.services.authorized_knowledge_index_contracts import (
    AuthorizedIndexWriteResult,
)
from backend.app.services.knowledge_authorization import (
    KnowledgeAclMutation,
    KnowledgeGrant,
    KnowledgeResourceIdentity,
    RetrievalAccessContext,
    set_local_knowledge_context,
)
from backend.app.services.knowledge_authorization.identity import (
    knowledge_resource_id,
    security_label_id,
)
from backend.app.services.knowledge_graph import bind_graph_visibility
from backend.app.services.knowledge_projection.retrievable.repository import (
    ProjectionWriteConflictError,
)
from backend.app.services.knowledge_projection.retrievable.write_contracts import (
    ExternalDocumentWrite,
    RetrievableProjectionWrite,
)


class AuthorizedKnowledgeIndexGenerationMixin:
    def _replace_generation(
        self,
        *,
        access_context: RetrievalAccessContext,
        identity: KnowledgeResourceIdentity,
        payload: RetrievableProjectionWrite,
        documents: tuple[ExternalDocumentWrite, ...],
        trusted_document: bool,
        acl_mutation: KnowledgeAclMutation | None = None,
        initial_grants: tuple[KnowledgeGrant, ...] = (),
    ) -> AuthorizedIndexWriteResult:
        expected_text_rows = sum(
            channel.row_count
            for channel in payload.channels
            if channel.modality == "text" and channel.state == "active"
        )
        if expected_text_rows != len(documents):
            raise ValueError("knowledge_projection_text_channel_row_mismatch")
        activation_status = (
            "degraded_channels"
            if any(
                channel.required and channel.state != "active"
                for channel in payload.channels
            )
            else "active"
        )
        if payload.graph_required and not payload.graph_complete:
            activation_status = "degraded_graph"
        model = next(
            (
                str(channel.model_revision)
                for channel in payload.channels
                if channel.modality == "text"
                and channel.state == "active"
                and channel.model_revision
            ),
            None,
        )
        resource_id = knowledge_resource_id(
            owner_capability_code=identity.owner_capability_code,
            source_kind=identity.source_kind,
            source_ref=identity.source_ref,
            owner_scope_type=identity.owner_scope_type,
            owner_scope_id=identity.owner_scope_id,
        )
        label_id = security_label_id(resource_id)
        connection = self._connection_factory()
        try:
            cursor = connection.cursor()
            set_local_knowledge_context(
                cursor,
                access_context,
                write_scope_type=identity.owner_scope_type,
                write_scope_id=identity.owner_scope_id,
                write_resource_id=resource_id,
                write_security_label_id=label_id,
            )
            if trusted_document:
                binding = (
                    self._authorization_service.ensure_trusted_document_resource(
                        cursor,
                        identity=identity,
                        access_context=access_context,
                    )
                )
            else:
                binding = self._authorization_service.ensure_project_resource(
                    cursor,
                    identity=identity,
                    access_context=access_context,
                    acl_mutation=acl_mutation,
                    initial_grants=initial_grants,
                )
            if (
                payload.graph is not None
                and payload.graph.visibility_partition_hash
                != binding.visibility_partition_hash
            ):
                payload = replace(
                    payload,
                    graph=bind_graph_visibility(
                        payload.graph,
                        visibility_partition_hash=(
                            binding.visibility_partition_hash
                        ),
                    ),
                )
            self._failpoint("resource_bound")
            projection_id, projection_created, already_active = (
                self._projection_repository.stage(
                    cursor,
                    identity=identity,
                    binding=binding,
                    payload=payload,
                )
            )
            self._failpoint("projection_staged")
            if already_active and not projection_created:
                cursor.execute(
                    """
                    SELECT COUNT(*)
                    FROM external_docs
                    WHERE projection_revision_id = %s
                      AND knowledge_resource_id = %s
                      AND security_label_id = %s
                    """,
                    (
                        projection_id,
                        binding.knowledge_resource_id,
                        binding.security_label_id,
                    ),
                )
                row = cursor.fetchone()
                if row is not None and int(row[0]) == len(documents):
                    connection.commit()
                    return self._result(
                        state="reused",
                        documents=len(documents),
                        revision_id=payload.source_revision,
                        model=model,
                        binding=binding,
                        projection_id=projection_id,
                    )
                raise ProjectionWriteConflictError(
                    "knowledge_projection_active_row_count_mismatch"
                )

            self._failpoint("before_channel_replace")
            inserted_count = self._text_channel_store.replace_generation(
                cursor,
                subject_user_id=access_context.subject_user_id,
                source_app=identity.source_app,
                binding=binding,
                projection_revision_id=projection_id,
                documents=documents,
            )
            self._failpoint("new_chunks_inserted")
            if inserted_count != len(documents):
                raise RuntimeError("knowledge_projection_chunk_count_mismatch")
            self._projection_repository.activate(
                cursor,
                projection_id=projection_id,
                resource_id=binding.knowledge_resource_id,
                embedding_profile_revision=payload.embedding_profile_revision,
                status=activation_status,
            )
            self._failpoint("projection_activated")
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

        return self._result(
            state=(
                "degraded"
                if activation_status
                in {"degraded_channels", "degraded_graph"}
                else "indexed"
            ),
            documents=len(documents),
            revision_id=payload.source_revision,
            model=model,
            binding=binding,
            projection_id=projection_id,
        )

    @staticmethod
    def _result(
        *,
        state: str,
        documents: int,
        revision_id: str,
        model: Optional[str],
        binding: Any,
        projection_id: str,
    ) -> AuthorizedIndexWriteResult:
        return AuthorizedIndexWriteResult(
            state=state,
            indexed_chunks=documents,
            revision_id=revision_id,
            embedding_model=model,
            knowledge_resource_id=binding.knowledge_resource_id,
            security_label_id=binding.security_label_id,
            projection_revision_id=projection_id,
            authz_revision=binding.authz_revision,
        )


__all__ = ["AuthorizedKnowledgeIndexGenerationMixin"]
