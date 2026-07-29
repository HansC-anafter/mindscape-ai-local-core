"""Thin post-commit trigger adapters for canonical object/artifact truth."""

from __future__ import annotations

from dataclasses import asdict
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from types import SimpleNamespace
from typing import Any, Iterable

from backend.app.models.object_runtime import ObjectInstanceRecord
from backend.app.services.knowledge_authorization.access_context_factory import (
    RetrievalAccessContextFactory,
)
from backend.app.services.knowledge_projection.facade import (
    KnowledgeProjectionFacade,
)

from .adapter_registry import get_adapter_registry
from .canonical_json import canonical_sha256
from .source_admission import RetrievableSourceAdmissionCommand


_MAX_OBJECTS_PER_ADMISSION_TASK = 20


@dataclass(frozen=True)
class CommittedSourceTriggerAuthority:
    actor_user_id: str
    active_group_id: str | None


_ACTIVE_TRIGGER_AUTHORITY: ContextVar[
    CommittedSourceTriggerAuthority | None
] = ContextVar("active_committed_source_trigger_authority", default=None)


@contextmanager
def committed_source_trigger_authority(
    *,
    actor_user_id: str,
    active_group_id: str | None,
):
    authority = CommittedSourceTriggerAuthority(
        actor_user_id=str(actor_user_id or "").strip(),
        active_group_id=str(active_group_id or "").strip() or None,
    )
    token = _ACTIVE_TRIGGER_AUTHORITY.set(authority)
    try:
        yield authority
    finally:
        _ACTIVE_TRIGGER_AUTHORITY.reset(token)


def current_committed_source_trigger_authority():
    return _ACTIVE_TRIGGER_AUTHORITY.get()


def admit_committed_object_records(
    *,
    workspace_id: str,
    actor_user_id: str,
    records: Iterable[ObjectInstanceRecord],
    active_group_id: str | None = None,
    facade: KnowledgeProjectionFacade | None = None,
    context_factory: RetrievalAccessContextFactory | None = None,
) -> dict[str, Any]:
    """Admit committed ObjectRefs by installed descriptor, never pack branch."""

    normalized_workspace = str(workspace_id or "").strip()
    normalized_actor = str(actor_user_id or "").strip()
    if not normalized_workspace or not normalized_actor:
        return {
            "state": "blocked",
            "reason": "knowledge_projection_trigger_identity_missing",
            "admitted_tasks": 0,
            "source_count": 0,
        }
    normalized_group = str(active_group_id or "").strip() or None
    factory = context_factory or RetrievalAccessContextFactory()
    auth = SimpleNamespace(
        user_id=normalized_actor,
        tenant_id="local",
        is_cloud_mode=False,
    )
    access_context = factory.build(
        auth,
        requested_workspace_ids=(
            ()
            if normalized_group is not None
            else (normalized_workspace,)
        ),
        requested_group_ids=(
            (normalized_group,) if normalized_group is not None else ()
        ),
    )
    registry = get_adapter_registry()
    grouped: dict[tuple[str, str], list[RetrievableSourceAdmissionCommand]] = {}
    unsupported = 0
    for record in records:
        ref = record.ref
        if ref.workspace_id and ref.workspace_id != normalized_workspace:
            raise ValueError(
                "knowledge_projection_object_workspace_mismatch"
            )
        descriptors = tuple(
            descriptor
            for descriptor in registry.list_capability(ref.owner_pack)
            if descriptor.source_kind == "object"
            and ref.object_kind in descriptor.object_kinds
            and "source_revision" in descriptor.trigger_modes
        )
        if not descriptors:
            unsupported += 1
            continue
        canonical_record = record.model_dump(
            mode="json",
            exclude_none=True,
        )
        content_hash = canonical_sha256(canonical_record)
        source_revision = str(
            ref.version or record.updated_at or content_hash
        )[:256]
        source_instance_id = str(ref.object_id or "").strip()
        if len(source_instance_id) > 128:
            source_instance_id = (
                "obj_" + canonical_sha256({"object_id": source_instance_id})[:48]
            )
        for descriptor in descriptors:
            command = RetrievableSourceAdmissionCommand(
                capability_code=descriptor.capability_code,
                capability_version=descriptor.capability_version,
                descriptor_id=descriptor.descriptor_id,
                descriptor_hash=descriptor.descriptor_hash,
                manifest_hash=descriptor.manifest_hash,
                source_kind="object",
                source_instance_id=source_instance_id,
                source_ref=ref.uri,
                source_revision=source_revision,
                content_hash=content_hash,
                evidence_type="aol_object_revision",
                evidence_id=(
                    "aol_" + canonical_sha256({"uri": ref.uri})[:48]
                ),
                workspace_id=normalized_workspace,
                group_id=normalized_group,
                object_kind=ref.object_kind,
                trigger_mode="source_revision",
                checkpoint={"object_uri": ref.uri},
                auto_triggered=True,
            )
            grouped.setdefault(
                (
                    descriptor.capability_code,
                    descriptor.descriptor_id,
                ),
                [],
            ).append(command)

    projection_facade = facade or KnowledgeProjectionFacade()
    receipts = []
    for key in sorted(grouped):
        commands = grouped[key]
        descriptor = registry.resolve(
            capability_code=commands[0].capability_code,
            capability_version=commands[0].capability_version,
            descriptor_id=commands[0].descriptor_id,
            descriptor_hash=commands[0].descriptor_hash,
            manifest_hash=commands[0].manifest_hash,
        )
        page_size = min(
            _MAX_OBJECTS_PER_ADMISSION_TASK,
            descriptor.limits.max_records_per_page,
        )
        for offset in range(0, len(commands), page_size):
            receipt = projection_facade.admit_retrievable_source_page(
                commands[offset : offset + page_size],
                access_context=access_context,
            )
            receipts.append(asdict(receipt))
    return {
        "state": (
            "admitted"
            if receipts
            else ("unsupported" if unsupported else "empty")
        ),
        "admitted_tasks": len(receipts),
        "source_count": sum(
            len(receipt.get("intake_ids") or ())
            for receipt in receipts
        ),
        "unsupported_source_count": unsupported,
        "receipts": receipts,
    }


def admit_committed_artifact_manifest(
    *,
    workspace_id: str,
    actor_user_id: str,
    capability_code: str,
    manifest: dict[str, Any],
    active_group_id: str | None = None,
    facade: KnowledgeProjectionFacade | None = None,
    context_factory: RetrievalAccessContextFactory | None = None,
) -> dict[str, Any]:
    """Admit exactly one committed Artifact Manifest through its pack adapter."""

    normalized_workspace = str(workspace_id or "").strip()
    normalized_actor = str(actor_user_id or "").strip()
    normalized_capability = str(capability_code or "").strip()
    if not normalized_workspace or not normalized_actor:
        return {
            "state": "blocked",
            "reason": "knowledge_projection_trigger_identity_missing",
        }
    if not normalized_capability:
        return {
            "state": "unsupported",
            "reason": "knowledge_projection_artifact_capability_missing",
        }
    artifact_id = str(manifest.get("artifact_id") or "").strip()
    checksum = str(manifest.get("checksum_sha256") or "").strip()
    if (
        not artifact_id
        or len(checksum) != 64
        or str(manifest.get("workspace_id") or "") != normalized_workspace
    ):
        return {
            "state": "blocked",
            "reason": "missing_canonical_manifest",
        }
    selector_candidates = {
        str(manifest.get("payload_schema") or "").strip(),
        str(manifest.get("mime_type") or "").strip(),
        "result_manifest",
    }
    registry = get_adapter_registry()
    descriptors = tuple(
        descriptor
        for descriptor in registry.list_capability(normalized_capability)
        if descriptor.source_kind == "artifact"
        and "source_revision" in descriptor.trigger_modes
        and bool(
            set(descriptor.artifact_selectors) & selector_candidates
        )
    )
    if not descriptors:
        return {
            "state": "unsupported",
            "reason": "knowledge_projection_artifact_descriptor_not_installed",
        }
    normalized_group = str(active_group_id or "").strip() or None
    factory = context_factory or RetrievalAccessContextFactory()
    access_context = factory.build(
        SimpleNamespace(
            user_id=normalized_actor,
            tenant_id="local",
            is_cloud_mode=False,
        ),
        requested_workspace_ids=(
            ()
            if normalized_group is not None
            else (normalized_workspace,)
        ),
        requested_group_ids=(
            (normalized_group,) if normalized_group is not None else ()
        ),
    )
    receipts = []
    projection_facade = facade or KnowledgeProjectionFacade()
    source_instance_id = artifact_id
    if len(source_instance_id) > 128:
        source_instance_id = (
            "artifact_"
            + canonical_sha256({"artifact_id": source_instance_id})[:48]
        )
    for descriptor in descriptors:
        selector = next(
            item
            for item in descriptor.artifact_selectors
            if item in selector_candidates
        )
        receipt = projection_facade.admit_retrievable_source(
            RetrievableSourceAdmissionCommand(
                capability_code=descriptor.capability_code,
                capability_version=descriptor.capability_version,
                descriptor_id=descriptor.descriptor_id,
                descriptor_hash=descriptor.descriptor_hash,
                manifest_hash=descriptor.manifest_hash,
                source_kind="artifact",
                source_instance_id=source_instance_id,
                source_ref=f"artifact_manifest:{artifact_id}",
                source_revision=checksum,
                content_hash=checksum,
                evidence_type="artifact_manifest",
                evidence_id=artifact_id[:256],
                workspace_id=normalized_workspace,
                group_id=normalized_group,
                artifact_selector=selector,
                trigger_mode="source_revision",
                checkpoint={
                    "object_key": str(
                        manifest.get("object_key") or ""
                    )[:1024],
                },
                auto_triggered=True,
            ),
            access_context=access_context,
        )
        receipts.append(asdict(receipt))
    return {
        "state": "admitted",
        "admitted_tasks": len(receipts),
        "source_count": 1,
        "receipts": receipts,
    }


def admit_artifact_landing(
    *,
    workspace_id: str,
    artifact_id: str,
    task_id: str | None,
    capability_code: str | None,
) -> dict[str, Any]:
    """Resolve committed manifest and server task identity after landing."""

    from backend.app.services.stores.postgres.artifact_manifest_store import (
        ArtifactManifestStore,
    )
    from backend.app.services.stores.tasks_store import TasksStore

    manifest = ArtifactManifestStore().get_result_manifest(
        artifact_id=artifact_id,
        workspace_id=workspace_id,
    )
    if manifest is None:
        return {"state": "blocked", "reason": "missing_canonical_manifest"}
    task = TasksStore().get_task(task_id) if task_id else None
    if task is None:
        return {
            "state": "blocked",
            "reason": "knowledge_projection_artifact_task_identity_missing",
        }
    execution_context = (
        task.execution_context
        if isinstance(task.execution_context, dict)
        else {}
    )
    snapshot = (
        execution_context.get("execution_admission_snapshot")
        if isinstance(
            execution_context.get("execution_admission_snapshot"),
            dict,
        )
        else {}
    )
    return admit_committed_artifact_manifest(
        workspace_id=workspace_id,
        actor_user_id=str(
            execution_context.get("profile_id")
            or task.params.get("actor_user_id")
            or ""
        ),
        capability_code=str(capability_code or task.pack_id or ""),
        manifest=manifest,
        active_group_id=str(snapshot.get("active_group_id") or "") or None,
    )


__all__ = [
    "CommittedSourceTriggerAuthority",
    "admit_artifact_landing",
    "admit_committed_artifact_manifest",
    "admit_committed_object_records",
    "committed_source_trigger_authority",
    "current_committed_source_trigger_authority",
]
