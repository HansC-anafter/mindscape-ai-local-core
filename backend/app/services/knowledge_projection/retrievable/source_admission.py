"""Atomic source-intake and existing-task-lane admission facade."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
from typing import Callable, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field

from backend.app.models.workspace import Task, TaskStatus
from backend.app.services.knowledge_authorization import (
    RetrievalAccessContext,
)
from backend.app.services.knowledge_projection.contracts import (
    KnowledgeSourceIntake,
)
from backend.app.services.knowledge_projection.source_ledger import (
    KnowledgeSourceLedgerFacade,
)
from backend.app.services.runner_topology import (
    KNOWLEDGE_INDEXING_QUEUE_PARTITION,
)
from backend.app.services.stores.tasks_store import TasksStore

from .adapter_registry import KnowledgeProjectionAdapterRegistry
from .internal_admission import build_internal_projection_admission
from .internal_admission_store import InternalProjectionAdmissionStore
from .task_payload import (
    DescriptorPointer,
    KnowledgeProjectionTaskPayload,
    SourcePointer,
)


INTERNAL_PROJECTION_TOOL = "knowledge.project_source"
Failpoint = Callable[[str], None]


class RetrievableSourceAdmissionCommand(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    capability_code: str = Field(pattern=r"^[a-z0-9_]+$")
    capability_version: str = Field(pattern=r"^\d+\.\d+\.\d+$")
    descriptor_id: str = Field(pattern=r"^[a-z0-9_]+$")
    descriptor_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    manifest_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    source_kind: Literal["object", "artifact", "memory", "document"]
    source_instance_id: str = Field(min_length=1, max_length=128)
    source_ref: str = Field(min_length=1, max_length=1024)
    source_revision: str = Field(min_length=1, max_length=256)
    content_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    evidence_type: str = Field(min_length=1, max_length=64)
    evidence_id: str = Field(min_length=1, max_length=256)
    workspace_id: str = Field(min_length=1, max_length=128)
    group_id: Optional[str] = Field(default=None, max_length=128)
    object_kind: Optional[str] = Field(default=None, max_length=128)
    artifact_selector: Optional[str] = Field(default=None, max_length=256)
    trigger_mode: Literal["source_revision", "explicit_reindex", "revoke"]
    checkpoint: dict = Field(default_factory=dict)
    auto_triggered: bool = True


@dataclass(frozen=True)
class RetrievableSourceAdmissionReceipt:
    state: str
    intake_id: Optional[str]
    task_id: Optional[str]
    intake_created: bool
    task_created: bool
    queue_shard: Optional[str]
    reason: Optional[str] = None
    intake_ids: tuple[str, ...] = ()


class RetrievableSourceAdmissionService:
    """Resolve one installed descriptor and atomically persist intake + task."""

    def __init__(
        self,
        *,
        registry: KnowledgeProjectionAdapterRegistry,
        source_ledger: KnowledgeSourceLedgerFacade | None = None,
        tasks_store: TasksStore | None = None,
        internal_admission_store: (
            InternalProjectionAdmissionStore | None
        ) = None,
        failpoint: Failpoint | None = None,
    ) -> None:
        self._registry = registry
        self._source_ledger = (
            source_ledger or KnowledgeSourceLedgerFacade()
        )
        self._tasks_store = tasks_store or TasksStore()
        self._internal_admission_store = (
            internal_admission_store
            or InternalProjectionAdmissionStore()
        )
        self._failpoint = failpoint or (lambda _step: None)

    def admit(
        self,
        command: RetrievableSourceAdmissionCommand,
        *,
        access_context: RetrievalAccessContext,
    ) -> RetrievableSourceAdmissionReceipt:
        return self.admit_page((command,), access_context=access_context)

    def admit_page(
        self,
        commands: tuple[RetrievableSourceAdmissionCommand, ...],
        *,
        access_context: RetrievalAccessContext,
    ) -> RetrievableSourceAdmissionReceipt:
        """Atomically create one bounded page task for one exact descriptor."""

        if not commands or len(commands) > 256:
            raise ValueError("knowledge_source_admission_page_size_invalid")
        ordered = tuple(
            sorted(
                commands,
                key=lambda item: (
                    item.source_instance_id,
                    item.source_revision,
                    item.content_hash,
                ),
            )
        )
        command = ordered[0]
        page_identity = (
            command.capability_code,
            command.capability_version,
            command.descriptor_id,
            command.descriptor_hash,
            command.manifest_hash,
            command.workspace_id,
            command.group_id,
            command.trigger_mode,
            command.auto_triggered,
        )
        if any(
            (
                item.capability_code,
                item.capability_version,
                item.descriptor_id,
                item.descriptor_hash,
                item.manifest_hash,
                item.workspace_id,
                item.group_id,
                item.trigger_mode,
                item.auto_triggered,
            )
            != page_identity
            for item in ordered
        ):
            raise ValueError(
                "knowledge_source_admission_page_identity_mismatch"
            )
        if len({item.source_instance_id for item in ordered}) != len(ordered):
            raise ValueError(
                "knowledge_source_admission_page_source_duplicate"
            )
        scope_type = "group" if command.group_id else "workspace"
        scope_id = command.group_id or command.workspace_id
        if not access_context.has_permission(
            "knowledge.project",
            scope_type=scope_type,
            scope_id=scope_id,
        ):
            raise PermissionError("knowledge_source_admission_permission_required")
        try:
            descriptor = self._registry.resolve(
                capability_code=command.capability_code,
                capability_version=command.capability_version,
                descriptor_id=command.descriptor_id,
                descriptor_hash=command.descriptor_hash,
                manifest_hash=command.manifest_hash,
            )
        except LookupError as exc:
            return RetrievableSourceAdmissionReceipt(
                state="unsupported",
                intake_id=None,
                task_id=None,
                intake_created=False,
                task_created=False,
                queue_shard=None,
                reason=str(exc),
                intake_ids=(),
            )
        if len(ordered) > min(
            descriptor.limits.max_records_per_page,
            256,
        ):
            raise ValueError(
                "knowledge_source_admission_descriptor_page_limit_exceeded"
            )
        for item in ordered:
            self._validate_descriptor_match(item, descriptor)
        intakes = tuple(
            KnowledgeSourceIntake(
                source_instance_id=item.source_instance_id,
                owner_type=scope_type,
                owner_id=scope_id,
                binding_id=item.descriptor_id,
                source_revision=item.source_revision,
                content_hash=item.content_hash,
                evidence_type=item.evidence_type,
                evidence_id=item.evidence_id,
                checkpoint=dict(item.checkpoint),
                visibility=(
                    "group" if item.group_id else "workspace"
                ),
                metadata={
                    "capability_code": item.capability_code,
                    "capability_version": item.capability_version,
                    "descriptor_id": item.descriptor_id,
                    "descriptor_hash": item.descriptor_hash,
                    "manifest_hash": item.manifest_hash,
                    "source_kind": item.source_kind,
                    "source_ref": item.source_ref,
                    "workspace_id": item.workspace_id,
                    "group_id": item.group_id,
                    "object_kind": item.object_kind,
                    "artifact_selector": item.artifact_selector,
                    "trigger_mode": item.trigger_mode,
                },
            )
            for item in ordered
        )
        intake_ids = tuple(
            self._source_ledger.prepare_intake(intake)
            for intake in intakes
        )
        task_id = self._task_id_page(intake_ids, command)
        internal_admission = build_internal_projection_admission(
            task_id=task_id,
            tenant_id=access_context.tenant_id,
            actor_user_id=access_context.subject_user_id,
            workspace_id=command.workspace_id,
            group_id=command.group_id,
            capability_code=command.capability_code,
            descriptor_id=command.descriptor_id,
            descriptor_hash=command.descriptor_hash,
            sources=[
                {
                    "intake_id": intake_id,
                    "source_instance_id": item.source_instance_id,
                    "source_revision": item.source_revision,
                    "content_hash": item.content_hash,
                }
                for intake_id, item in zip(intake_ids, ordered)
            ],
            trigger_mode=command.trigger_mode,
        )
        source_page = tuple(
            SourcePointer(
                source_kind=item.source_kind,
                source_instance_id=item.source_instance_id,
                source_ref=item.source_ref,
                source_revision=item.source_revision,
                content_hash=item.content_hash,
                object_kind=item.object_kind,
                artifact_selector=item.artifact_selector,
            )
            for item in ordered
        )
        payload = KnowledgeProjectionTaskPayload(
            internal_task_id=task_id,
            intake_id=intake_ids[0],
            actor_user_id=access_context.subject_user_id,
            tenant_id=access_context.tenant_id,
            workspace_id=command.workspace_id,
            group_id=command.group_id,
            trigger_mode=command.trigger_mode,
            descriptor=DescriptorPointer(
                capability_code=command.capability_code,
                capability_version=command.capability_version,
                descriptor_id=command.descriptor_id,
                descriptor_hash=command.descriptor_hash,
                manifest_hash=command.manifest_hash,
            ),
            source=source_page[0],
            sources=source_page,
            checkpoint=(
                dict(command.checkpoint)
                if len(ordered) == 1
                else {
                    "source_checkpoints": [
                        {
                            "source_instance_id": item.source_instance_id,
                            "checkpoint": dict(item.checkpoint),
                        }
                        for item in ordered
                    ]
                }
            ),
        )
        task = Task(
            id=task_id,
            workspace_id=command.workspace_id,
            message_id=(
                f"knowledge-intake-page:{intake_ids[0]}:{len(intake_ids)}"
            ),
            execution_id=task_id,
            pack_id=INTERNAL_PROJECTION_TOOL,
            task_type="tool_execution",
            status=TaskStatus.PENDING,
            params=payload.bounded_dict(),
            execution_context={
                "tool_name": INTERNAL_PROJECTION_TOOL,
                "root_execution_id": task_id,
                "queue_partition": KNOWLEDGE_INDEXING_QUEUE_PARTITION,
                "queue_shard": KNOWLEDGE_INDEXING_QUEUE_PARTITION,
                "auto_triggered": command.auto_triggered,
                "admission_policy": {
                    "mode": (
                        "auto" if command.auto_triggered else "manual"
                    ),
                    "visibility": (
                        "background"
                        if command.auto_triggered
                        else "visible"
                    ),
                    "producer_kind": "knowledge_projection",
                },
                "single_flight_key": task_id,
                "capability_code": command.capability_code,
                "knowledge_projection_admission": (
                    internal_admission.model_dump(mode="json")
                ),
            },
            queue_shard=KNOWLEDGE_INDEXING_QUEUE_PARTITION,
        )
        self._tasks_store.prepare_task_for_create(task)
        with self._tasks_store.transaction() as conn:
            intake_receipts = tuple(
                self._source_ledger.record_intake_with_conn(
                    conn,
                    intake,
                    intake_id=intake_id,
                )
                for intake, intake_id in zip(intakes, intake_ids)
            )
            self._failpoint("intake_written")
            task, task_created = self._tasks_store.create_task_with_conn(
                conn,
                task,
                already_prepared=True,
                idempotent=True,
            )
            self._failpoint("task_written")
            self._internal_admission_store.record_with_conn(
                conn,
                internal_admission,
            )
            self._failpoint("internal_admission_written")
        self._tasks_store.finalize_task_create_after_commit(
            task,
            created=task_created,
        )
        task_retried = False
        if not task_created and command.trigger_mode == "explicit_reindex":
            retried = (
                self._tasks_store.retry_terminal_task_after_commit(
                    task.id
                )
            )
            if retried is not None:
                task = retried
                task_retried = True
        state = (
            "deferred"
            if task.blocked_reason == "admission_deferred"
            else (
                "retried"
                if task_retried
                else ("admitted" if task_created else "reused")
            )
        )
        return RetrievableSourceAdmissionReceipt(
            state=state,
            intake_id=intake_receipts[0].intake_id,
            task_id=task.id,
            intake_created=all(
                receipt.created for receipt in intake_receipts
            ),
            task_created=task_created,
            queue_shard=task.queue_shard,
            reason=task.blocked_reason,
            intake_ids=tuple(
                receipt.intake_id for receipt in intake_receipts
            ),
        )

    @staticmethod
    def _validate_descriptor_match(command, descriptor) -> None:
        if descriptor.source_kind != command.source_kind:
            raise ValueError("knowledge_source_descriptor_kind_mismatch")
        if command.trigger_mode not in descriptor.trigger_modes:
            raise ValueError("knowledge_source_trigger_not_supported")
        if command.source_kind == "object":
            if command.object_kind not in descriptor.object_kinds:
                raise ValueError("knowledge_source_object_kind_not_supported")
        elif command.object_kind is not None:
            raise ValueError("knowledge_source_object_kind_forbidden")
        if command.source_kind == "artifact":
            if command.artifact_selector not in descriptor.artifact_selectors:
                raise ValueError(
                    "knowledge_source_artifact_selector_not_supported"
                )
        elif command.artifact_selector is not None:
            raise ValueError("knowledge_source_artifact_selector_forbidden")

    @staticmethod
    def _task_id(
        intake_id: str,
        command: RetrievableSourceAdmissionCommand,
    ) -> str:
        digest = hashlib.sha256(
            (
                f"{intake_id}\x1f{command.descriptor_hash}\x1f"
                f"{command.trigger_mode}"
            ).encode("utf-8")
        ).hexdigest()
        return f"ktask_{digest}"

    @staticmethod
    def _task_id_page(
        intake_ids: tuple[str, ...],
        command: RetrievableSourceAdmissionCommand,
    ) -> str:
        if len(intake_ids) == 1:
            return RetrievableSourceAdmissionService._task_id(
                intake_ids[0],
                command,
            )
        digest = hashlib.sha256(
            (
                "\x1e".join(intake_ids)
                + f"\x1f{command.descriptor_hash}\x1f"
                + command.trigger_mode
            ).encode("utf-8")
        ).hexdigest()
        return f"ktask_{digest}"


__all__ = [
    "INTERNAL_PROJECTION_TOOL",
    "RetrievableSourceAdmissionCommand",
    "RetrievableSourceAdmissionReceipt",
    "RetrievableSourceAdmissionService",
]
