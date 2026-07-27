"""Pack-neutral builder used by capability-owned object compilers."""

from __future__ import annotations

import inspect
import json
from typing import Any, Awaitable, Callable, Mapping

from backend.app.services.knowledge_authorization import (
    KnowledgeGrant,
    KnowledgeResourceIdentity,
    PrincipalRef,
    visibility_partition_hash_for_grants,
)
from backend.app.services.knowledge_graph.community import (
    build_visibility_partitioned_communities,
)
from backend.app.services.knowledge_graph.contracts import (
    GraphCommunityReportWrite,
    GraphEntityWrite,
    GraphMentionWrite,
    GraphProjectionWrite,
    GraphRelationWrite,
)
from backend.app.services.knowledge_projection.retrievable.canonical_json import (
    canonical_sha256,
)
from backend.app.services.knowledge_projection.retrievable.pack_compiler_values import (
    bounded_owner_value,
    facet_rows,
    media_pointer,
    target_key,
)
from backend.app.services.knowledge_projection.retrievable.task_payload import (
    KnowledgeProjectionTaskPayload,
)
from backend.app.services.knowledge_projection.retrievable.text_compatibility import (
    fit_external_docs_embedding,
)
from backend.app.services.knowledge_projection.retrievable.write_contracts import (
    ExternalDocumentWrite,
    ProjectionChannelWrite,
    ProjectionEvidenceWrite,
    ProjectionRecordWrite,
    RetrievableProjectionWrite,
)
from backend.app.services.tools.knowledge_project_source import (
    ProjectionCompilerOutput,
    ProjectionCompilerPageOutput,
)
from backend.app.services.vector_search import VectorSearchService


ObjectResolver = Callable[..., Mapping[str, Any]]
EmbeddingProvider = Callable[
    [str],
    Awaitable[tuple[list[float], str]] | tuple[list[float], str],
]


async def compile_owner_object_projection(
    payload: KnowledgeProjectionTaskPayload,
    *,
    capability_code: str,
    detail_resolvers: Mapping[str, ObjectResolver],
    graph_resolvers: Mapping[str, ObjectResolver],
    compiler_revision: str,
    embedding_provider: EmbeddingProvider | None = None,
) -> ProjectionCompilerOutput | ProjectionCompilerPageOutput:
    """Hydrate pointer-only AOL objects and emit complete generations."""

    if payload.descriptor.capability_code != capability_code:
        raise ValueError("knowledge_pack_compiler_capability_mismatch")
    provider = embedding_provider
    if provider is None:
        vector_service = VectorSearchService()

        async def provider(text: str) -> tuple[list[float], str]:
            return await vector_service._generate_embedding_with_model(
                text
            )

    outputs = []
    for source in payload.source_page:
        if source.source_kind != "object" or not source.object_kind:
            raise ValueError("knowledge_pack_compiler_object_required")
        detail_resolver = detail_resolvers.get(source.object_kind)
        graph_resolver = graph_resolvers.get(source.object_kind)
        if detail_resolver is None or graph_resolver is None:
            raise ValueError(
                "knowledge_pack_compiler_object_kind_unsupported"
            )
        detail = dict(
            detail_resolver(
                workspace_id=payload.workspace_id,
                object_id=source.source_instance_id,
            )
        )
        graph_payload = dict(
            graph_resolver(
                workspace_id=payload.workspace_id,
                object_id=source.source_instance_id,
            )
        )
        portable = {
            "object_kind": source.object_kind,
            "detail": bounded_owner_value(detail),
            "graph": bounded_owner_value(graph_payload),
        }
        content = json.dumps(
            portable,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )[:32768]
        embedded = provider(content)
        if inspect.isawaitable(embedded):
            embedded = await embedded
        raw_embedding, model_name = embedded
        embedding = fit_external_docs_embedding(raw_embedding)
        if not embedding or not model_name:
            raise ValueError(
                "knowledge_pack_compiler_text_embedding_unavailable"
            )
        content_hash = canonical_sha256(content)
        citation = {
            "source_ref": source.source_ref,
            "source_revision": source.source_revision,
            "content_hash": source.content_hash,
            "anchor": {"kind": "object", "object_id": source.source_instance_id},
        }
        evidence = [
            ProjectionEvidenceWrite(
                unit_key="text-1",
                unit_kind="text_span",
                owner_asset_ref=source.source_ref,
                content_hash=content_hash,
                media_type="text/plain",
                anchor={
                    "kind": "text_span",
                    "start": 0,
                    "end": len(content),
                },
            )
        ]
        channels = [
            ProjectionChannelWrite(
                unit_key="text-1",
                channel_id="text.semantic",
                modality="text",
                profile_revision=compiler_revision,
                model_revision=str(model_name),
                dimension=len(embedding),
                calibration_revision="cosine.v1",
                index_revision=f"external_docs.{compiler_revision}",
                required=True,
                state="active",
                row_count=1,
                byte_count=len(embedding) * 4,
                physical_store_ref="external_docs",
            )
        ]
        media = media_pointer(detail)
        if media is not None:
            modality, pointer = media
            unit_kind = {
                "image": "image_region",
                "video": "video_segment",
                "audio": "audio_segment",
            }[modality]
            evidence.append(
                ProjectionEvidenceWrite(
                    unit_key=f"{modality}-1",
                    unit_kind=unit_kind,
                    owner_asset_ref=pointer,
                    content_hash=canonical_sha256(
                        {
                            "pointer": pointer,
                            "source_hash": source.content_hash,
                        }
                    ),
                    media_type={
                        "image": "image/*",
                        "video": "video/*",
                        "audio": "audio/*",
                    }[modality],
                    anchor={"kind": unit_kind, "owner_pointer": pointer},
                    derivative_refs=(
                        {
                            "kind": "text_derivative",
                            "evidence_unit_key": "text-1",
                            "revision": compiler_revision,
                        },
                    ),
                )
            )
            channels.append(
                ProjectionChannelWrite(
                    unit_key=f"{modality}-1",
                    channel_id=f"{modality}.native",
                    modality=modality,
                    profile_revision=compiler_revision,
                    model_revision=None,
                    dimension=None,
                    calibration_revision=None,
                    index_revision=None,
                    required=False,
                    state="not_admitted",
                    row_count=0,
                    byte_count=0,
                    reason="native_modality_channel_not_admitted",
                    physical_store_ref=pointer,
                )
            )
        source_entity_key = source.source_ref
        entities: dict[str, GraphEntityWrite] = {
            source_entity_key: GraphEntityWrite(
                source_entity_key,
                str(graph_payload.get("node_kind") or source.object_kind),
                "owner_object_ref.v1",
            )
        }
        relations = []
        for index, relation in enumerate(
            list(graph_payload.get("relations") or [])[:256]
        ):
            if not isinstance(relation, Mapping):
                continue
            target = relation.get("target_ref")
            if not isinstance(target, Mapping):
                continue
            resolved_target_key = target_key(target)
            relation_kind = str(
                relation.get("relation_kind") or ""
            ).strip()
            if not resolved_target_key or not relation_kind:
                continue
            entities.setdefault(
                resolved_target_key,
                GraphEntityWrite(
                    resolved_target_key,
                    str(target.get("object_kind") or "external_object"),
                    "owner_object_ref.v1",
                ),
            )
            relations.append(
                GraphRelationWrite(
                    relation_key=(
                        "owner:"
                        + canonical_sha256(
                            {
                                "source": source_entity_key,
                                "target": resolved_target_key,
                                "kind": relation_kind,
                                "ordinal": index,
                            }
                        )
                    ),
                    source_entity_key=source_entity_key,
                    target_entity_key=resolved_target_key,
                    relation_kind=relation_kind,
                    origin="owner_declared",
                    confidence=1.0,
                    supporting_evidence_unit_keys=("text-1",),
                    supporting_citations=(citation,),
                    owner_relation_revision=source.source_revision,
                )
            )
        grants = (
            KnowledgeGrant(
                PrincipalRef("user", payload.actor_user_id),
                relation="owner",
            ),
        )
        visibility_hash = visibility_partition_hash_for_grants(grants)
        communities = build_visibility_partitioned_communities(
            entities=tuple(entities.values()),
            relations=tuple(relations),
            visibility_partition_hash=visibility_hash,
        )
        summary = str(
            graph_payload.get("summary_text")
            or graph_payload.get("display_label")
            or detail.get("display_label")
            or source.source_ref
        )[:4096]
        reports = tuple(
            GraphCommunityReportWrite(
                community_key=community.community_key,
                summary=summary,
                findings=tuple(
                    {
                        "relation_kind": relation.relation_kind,
                        "target": relation.target_entity_key,
                    }
                    for relation in relations
                    if relation.relation_key
                    in community.relation_keys
                ),
                rank=1.0,
                supporting_citations=(citation,),
                model_revision="owner_declared.no_llm.v1",
                prompt_revision="owner_declared.no_prompt.v1",
            )
            for community in communities
        )
        graph = GraphProjectionWrite(
            algorithm_revision="connected_components.v1",
            resolver_revision="owner_object_ref.v1",
            visibility_partition_hash=visibility_hash,
            entities=tuple(entities.values()),
            mentions=(
                GraphMentionWrite(
                    entity_key=source_entity_key,
                    evidence_unit_key="text-1",
                    record_key="object-1",
                    surface_text=summary,
                    mention_type=str(
                        graph_payload.get("node_kind")
                        or source.object_kind
                    ),
                    confidence=1.0,
                    citation=citation,
                    extractor_revision="owner_declared.v1",
                    model_revision="owner_declared.no_llm.v1",
                    prompt_revision="owner_declared.no_prompt.v1",
                ),
            ),
            relations=tuple(relations),
            communities=communities,
            reports=reports,
        )
        projection_hash = canonical_sha256(
            {
                "source": source.model_dump(mode="json"),
                "portable": portable,
                "compiler_revision": compiler_revision,
                "model_name": model_name,
            }
        )
        outputs.append(
            ProjectionCompilerOutput(
                identity=KnowledgeResourceIdentity(
                    tenant_id=payload.tenant_id,
                    owner_capability_code=capability_code,
                    source_kind="object",
                    source_app=capability_code,
                    source_id=source.source_instance_id,
                    source_ref=source.source_ref,
                    source_revision=source.source_revision,
                    owner_scope_type=(
                        "group" if payload.group_id else "workspace"
                    ),
                    owner_scope_id=(
                        payload.group_id or payload.workspace_id
                    ),
                    classification=(
                        "group" if payload.group_id else "workspace"
                    ),
                ),
                projection=RetrievableProjectionWrite(
                    source_instance_id=source.source_instance_id,
                    source_revision=source.source_revision,
                    content_hash=source.content_hash,
                    descriptor_id=payload.descriptor.descriptor_id,
                    descriptor_revision=(
                        payload.descriptor.descriptor_hash
                    ),
                    projector_revision=compiler_revision,
                    facet_schema_revision=f"{capability_code}.object.v1",
                    embedding_profile_revision=str(model_name),
                    projection_hash=projection_hash,
                    evidence_units=tuple(evidence),
                    channels=tuple(channels),
                    records=(
                        ProjectionRecordWrite(
                            record_kind=source.object_kind,
                            record_key="object-1",
                            search_text=content,
                            citation=citation,
                            values=dict(bounded_owner_value(detail)),
                            content_hash=content_hash,
                            facets=facet_rows(
                                detail,
                                object_kind=source.object_kind,
                            ),
                        ),
                    ),
                    relation_count=len(relations),
                    graph_complete=True,
                    graph_required=True,
                    graph=graph,
                ),
                documents=(
                    ExternalDocumentWrite(
                        source_id=(
                            f"{source.source_instance_id}:"
                            f"{source.source_revision}:text-1"
                        ),
                        doc_type=source.object_kind,
                        title=summary,
                        content=content,
                        embedding=tuple(embedding),
                        metadata={
                            "workspace_id": payload.workspace_id,
                            "group_id": payload.group_id,
                            "chunk_id": "text-1",
                            "active": True,
                            "embedding_model": str(model_name),
                            "pipeline_version": compiler_revision,
                            "owner_asset_ref": source.source_ref,
                            "media_type": "text/plain",
                        },
                    ),
                ),
            )
        )
    if len(outputs) == 1:
        return outputs[0]
    return ProjectionCompilerPageOutput(outputs=tuple(outputs))


__all__ = ["compile_owner_object_projection"]
