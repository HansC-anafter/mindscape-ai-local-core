from pathlib import Path
from backend.app.models.object_runtime import ObjectInstanceRecord, ObjectRef
from backend.app.services.knowledge_projection.retrievable.adapter_registry import (
    get_adapter_registry,
)
from backend.app.services.knowledge_projection.retrievable.source_triggers import (
    admit_committed_artifact_manifest,
    admit_committed_object_records,
)
from backend.app.services.knowledge_projection.retrievable.source_admission import (
    RetrievableSourceAdmissionReceipt,
)


class _ContextFactory:
    def __init__(self):
        self.calls = []

    def build(self, auth, **kwargs):
        self.calls.append((auth, kwargs))
        return object()


class _Facade:
    def __init__(self):
        self.pages = []

    def admit_retrievable_source_page(self, commands, *, access_context):
        self.pages.append((tuple(commands), access_context))
        return RetrievableSourceAdmissionReceipt(
            state="admitted",
            intake_id="intake-one",
            task_id="task-one",
            intake_created=True,
            task_created=True,
            queue_shard="knowledge_indexing",
            reason=None,
            intake_ids=tuple(
                f"intake-{index}"
                for index, _item in enumerate(commands, start=1)
            ),
        )

    def admit_retrievable_source(self, command, *, access_context):
        self.pages.append(((command,), access_context))
        return RetrievableSourceAdmissionReceipt(
            state="admitted",
            intake_id="artifact-intake",
            task_id="artifact-task",
            intake_created=True,
            task_created=True,
            queue_shard="knowledge_indexing",
            intake_ids=("artifact-intake",),
        )


def test_object_trigger_groups_records_into_one_pack_neutral_page():
    registry = get_adapter_registry()
    registry.unregister_capability("trigger_pack")
    registry.register_manifest(
        "trigger_pack",
        {
            "code": "trigger_pack",
            "version": "1.0.0",
            "object_exports": [{"kind": "trigger.asset"}],
            "knowledge_projections": [
                {
                    "id": "asset_projection",
                    "source_kind": "object",
                    "object_kinds": ["trigger.asset"],
                    "contract_version": "1.0.0",
                    "compiler_backend": (
                        "capabilities.trigger_pack.projections.compiler:"
                        "compile_asset"
                    ),
                    "projection_profiles": ["semantic_text"],
                    "evidence_unit_kinds": ["text_span"],
                    "trigger_modes": ["source_revision"],
                    "limits": {
                        "max_chunks": 100,
                        "max_records_per_page": 100,
                    },
                }
            ],
        },
        Path("/tmp/trigger-pack"),
    )
    facade = _Facade()
    context_factory = _ContextFactory()
    records = [
        ObjectInstanceRecord(
            ref=ObjectRef(
                uri=f"mindscape://trigger_pack/trigger.asset/asset-{index}",
                owner_pack="trigger_pack",
                object_kind="trigger.asset",
                object_id=f"asset-{index}",
                workspace_id="workspace-one",
                version="revision-one",
            ),
            title=f"Asset {index}",
        )
        for index in range(2)
    ]
    try:
        result = admit_committed_object_records(
            workspace_id="workspace-one",
            actor_user_id="owner-one",
            records=records,
            facade=facade,
            context_factory=context_factory,
        )
    finally:
        registry.unregister_capability("trigger_pack")

    assert result["state"] == "admitted"
    assert result["admitted_tasks"] == 1
    assert result["source_count"] == 2
    assert len(facade.pages) == 1
    commands, _context = facade.pages[0]
    assert {item.source_instance_id for item in commands} == {
        "asset-0",
        "asset-1",
    }
    assert len(context_factory.calls) == 1


def test_artifact_trigger_requires_committed_manifest_and_exact_selector():
    registry = get_adapter_registry()
    registry.unregister_capability("artifact_pack")
    registry.register_manifest(
        "artifact_pack",
        {
            "code": "artifact_pack",
            "version": "1.0.0",
            "knowledge_projections": [
                {
                    "id": "result_projection",
                    "source_kind": "artifact",
                    "artifact_selectors": ["task_result"],
                    "contract_version": "1.0.0",
                    "compiler_backend": (
                        "capabilities.artifact_pack.projections.compiler:"
                        "compile_result"
                    ),
                    "projection_profiles": ["semantic_text"],
                    "evidence_unit_kinds": ["text_span"],
                    "trigger_modes": ["source_revision"],
                    "limits": {
                        "max_chunks": 100,
                        "max_records_per_page": 100,
                    },
                }
            ],
        },
        Path("/tmp/artifact-pack"),
    )
    facade = _Facade()
    context_factory = _ContextFactory()
    try:
        result = admit_committed_artifact_manifest(
            workspace_id="workspace-one",
            actor_user_id="owner-one",
            capability_code="artifact_pack",
            manifest={
                "artifact_id": "artifact-one",
                "workspace_id": "workspace-one",
                "checksum_sha256": "a" * 64,
                "payload_schema": "task_result",
                "mime_type": "application/json",
                "object_key": "results/artifact-one.json",
            },
            facade=facade,
            context_factory=context_factory,
        )
    finally:
        registry.unregister_capability("artifact_pack")

    assert result["state"] == "admitted"
    assert result["admitted_tasks"] == 1
    command = facade.pages[0][0][0]
    assert command.source_kind == "artifact"
    assert command.artifact_selector == "task_result"
    assert command.source_revision == "a" * 64
