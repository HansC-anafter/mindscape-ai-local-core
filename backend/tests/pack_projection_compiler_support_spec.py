"""Pack substitution acceptance for the neutral compiler builder."""

import pytest

from backend.app.services.knowledge_authorization import (
    KnowledgeGrant,
    PrincipalRef,
    visibility_partition_hash_for_grants,
)
from backend.app.services.knowledge_graph import bind_graph_visibility
from backend.app.services.knowledge_projection.retrievable.pack_compiler_support import (
    compile_owner_object_projection,
)
from backend.app.services.knowledge_projection.retrievable.task_payload import (
    DescriptorPointer,
    KnowledgeProjectionTaskPayload,
    SourcePointer,
)
from backend.app.services.tools.knowledge_project_source import (
    ProjectionCompilerOutput,
)


def _detail(*, workspace_id: str, object_id: str):
    return {
        "workspace_id": workspace_id,
        "object_id": object_id,
        "display_label": "Reference one",
        "status": "ready",
        "image_url": f"/media/{object_id}.png",
    }


def _graph(*, workspace_id: str, object_id: str):
    return {
        "node_kind": "reference",
        "display_label": "Reference one",
        "summary_text": "Reference one is linked to a creative space.",
        "relations": [
            {
                "relation_kind": "assigned_to",
                "target_ref": {
                    "uri": "mindscape://synthetic_pack/creative_space/space-1",
                    "owner_pack": "synthetic_pack",
                    "object_kind": "creative_space",
                    "object_id": "space-1",
                    "workspace_id": workspace_id,
                },
            }
        ],
    }


@pytest.mark.asyncio
async def test_object_projection_is_graph_complete_and_multimodal_truthful() -> None:
    source = SourcePointer(
        source_kind="object",
        source_instance_id="reference-1",
        source_ref="mindscape://synthetic_pack/reference/reference-1",
        source_revision="revision-1",
        content_hash="c" * 64,
        object_kind="reference",
    )
    payload = KnowledgeProjectionTaskPayload(
        internal_task_id="task-1",
        intake_id="intake-1",
        actor_user_id="owner-1",
        tenant_id="local",
        workspace_id="workspace-1",
        trigger_mode="source_revision",
        descriptor=DescriptorPointer(
            capability_code="synthetic_pack",
            capability_version="1.0.0",
            descriptor_id="synthetic_objects_v1",
            descriptor_hash="a" * 64,
            manifest_hash="b" * 64,
        ),
        source=source,
    )

    async def embed(_text: str):
        return [1.0, 0.0], "synthetic-embedding.v1"

    compiled = await compile_owner_object_projection(
        payload,
        capability_code="synthetic_pack",
        detail_resolvers={"reference": _detail},
        graph_resolvers={"reference": _graph},
        compiler_revision="synthetic.object_projection.v1",
        embedding_provider=embed,
    )

    assert isinstance(compiled, ProjectionCompilerOutput)
    assert compiled.identity.source_id == "reference-1"
    assert compiled.projection.graph_complete is True
    assert compiled.projection.relation_count == 1
    assert len(compiled.projection.graph.communities) == 1
    assert len(compiled.projection.graph.reports) == 1
    channels = {
        (channel.modality, channel.state)
        for channel in compiled.projection.channels
    }
    assert ("text", "active") in channels
    assert ("image", "not_admitted") in channels
    assert len(compiled.documents[0].embedding) == 1536

    group_visibility = visibility_partition_hash_for_grants(
        (
            KnowledgeGrant(
                PrincipalRef("user", "owner-1"),
                relation="owner",
            ),
            KnowledgeGrant(
                PrincipalRef("group_role", "group-1:member"),
                relation="reader",
            ),
        )
    )
    rebound = bind_graph_visibility(
        compiled.projection.graph,
        visibility_partition_hash=group_visibility,
    )
    assert rebound.visibility_partition_hash == group_visibility
    assert rebound.entities == compiled.projection.graph.entities
    assert rebound.relations == compiled.projection.graph.relations
    assert (
        rebound.communities[0].entity_keys
        == compiled.projection.graph.communities[0].entity_keys
    )
    assert (
        rebound.communities[0].community_key
        != compiled.projection.graph.communities[0].community_key
    )
    assert (
        rebound.reports[0].community_key
        == rebound.communities[0].community_key
    )
