"""Runner-internal tool for one pinned retrievable projection task."""

from __future__ import annotations

import importlib
import inspect
from contextvars import ContextVar
from dataclasses import dataclass
from typing import Awaitable, Callable

from backend.app.services.knowledge_authorization import (
    KnowledgeAclMutation,
    KnowledgePermission,
    KnowledgeResourceIdentity,
    PrincipalRef,
    RetrievalAccessContext,
)
from backend.app.services.knowledge_projection.facade import (
    KnowledgeProjectionFacade,
)
from backend.app.services.knowledge_projection.retrievable.adapter_registry import (
    get_adapter_registry,
)
from backend.app.services.knowledge_projection.retrievable.source_admission import (
    INTERNAL_PROJECTION_TOOL,
)
from backend.app.services.knowledge_projection.retrievable.task_payload import (
    KnowledgeProjectionTaskPayload,
)
from backend.app.services.knowledge_projection.retrievable.write_contracts import (
    ExternalDocumentWrite,
    RetrievableProjectionWrite,
)
from backend.app.services.tools.base import MindscapeTool
from backend.app.services.tools.internal_execution import (
    require_internal_tool_authority,
)
from backend.app.services.tools.schemas import ToolInputSchema, ToolMetadata


@dataclass(frozen=True)
class ProjectionCompilerOutput:
    identity: KnowledgeResourceIdentity
    projection: RetrievableProjectionWrite
    documents: tuple[ExternalDocumentWrite, ...] = ()
    acl_mutation: KnowledgeAclMutation | None = None


@dataclass(frozen=True)
class ProjectionCompilerPageOutput:
    outputs: tuple[ProjectionCompilerOutput, ...]


ProjectionCompiler = Callable[
    [KnowledgeProjectionTaskPayload],
    ProjectionCompilerOutput
    | ProjectionCompilerPageOutput
    | Awaitable[ProjectionCompilerOutput | ProjectionCompilerPageOutput],
]
_ACTIVE_PROJECTION_TASK: ContextVar[str | None] = ContextVar(
    "active_knowledge_projection_task",
    default=None,
)


class KnowledgeProjectSourceTool(MindscapeTool):
    """Hydrate through a capability-owned compiler, then call the one writer."""

    def __init__(
        self,
        facade: KnowledgeProjectionFacade | None = None,
    ) -> None:
        self._facade = facade
        super().__init__(
            ToolMetadata(
                name=INTERNAL_PROJECTION_TOOL,
                description=(
                    "Runner-internal projection of one server-admitted source "
                    "pointer through its pinned installed descriptor."
                ),
                input_schema=ToolInputSchema(
                    type="object",
                    properties={
                        "contract_version": {"type": "string"},
                        "internal_task_id": {"type": "string"},
                        "intake_id": {"type": "string"},
                        "actor_user_id": {"type": "string"},
                        "tenant_id": {"type": "string"},
                        "workspace_id": {"type": "string"},
                        "group_id": {"type": "string"},
                        "trigger_mode": {"type": "string"},
                        "descriptor": {"type": "object"},
                        "source": {"type": "object"},
                        "sources": {
                            "type": "array",
                            "maxItems": 256,
                            "items": {"type": "object"},
                        },
                        "checkpoint": {"type": "object"},
                    },
                    required=[
                        "contract_version",
                        "internal_task_id",
                        "intake_id",
                        "actor_user_id",
                        "tenant_id",
                        "workspace_id",
                        "trigger_mode",
                        "descriptor",
                        "source",
                    ],
                ),
                category="data",
                source_type="builtin",
                provider="knowledge_foundation",
                danger_level="medium",
                internal=True,
            )
        )

    async def execute(self, **kwargs):
        payload = KnowledgeProjectionTaskPayload.model_validate(kwargs)
        require_internal_tool_authority(
            task_id=payload.internal_task_id,
            tool_name=INTERNAL_PROJECTION_TOOL,
        )
        if _ACTIVE_PROJECTION_TASK.get() is not None:
            raise RuntimeError("knowledge_projection_recursive_execution_forbidden")
        active_token = _ACTIVE_PROJECTION_TASK.set(payload.internal_task_id)
        try:
            return await self._execute_admitted(payload)
        finally:
            _ACTIVE_PROJECTION_TASK.reset(active_token)

    async def _execute_admitted(self, payload: KnowledgeProjectionTaskPayload):
        descriptor = get_adapter_registry().resolve(
            capability_code=payload.descriptor.capability_code,
            capability_version=payload.descriptor.capability_version,
            descriptor_id=payload.descriptor.descriptor_id,
            descriptor_hash=payload.descriptor.descriptor_hash,
            manifest_hash=payload.descriptor.manifest_hash,
        )
        if (
            descriptor.source_kind != payload.source.source_kind
            or payload.trigger_mode not in descriptor.trigger_modes
        ):
            raise ValueError("knowledge_projection_pinned_descriptor_mismatch")
        scope_type = "group" if payload.group_id else "workspace"
        scope_id = payload.group_id or payload.workspace_id
        context = RetrievalAccessContext.create(
            subject_user_id=payload.actor_user_id,
            tenant_id=payload.tenant_id,
            principals=(PrincipalRef("user", payload.actor_user_id),),
            permissions=(
                KnowledgePermission(
                    "knowledge.project",
                    scope_type,
                    scope_id,
                ),
            ),
        )
        facade = self._facade or KnowledgeProjectionFacade()
        if payload.trigger_mode == "revoke":
            revoke_results = tuple(
                facade.revoke_retrievable(
                    access_context=context,
                    identity=KnowledgeResourceIdentity(
                        tenant_id=payload.tenant_id,
                        owner_capability_code=(
                            payload.descriptor.capability_code
                        ),
                        source_kind=source.source_kind,
                        source_app=payload.descriptor.capability_code,
                        source_id=source.source_instance_id,
                        source_ref=source.source_ref,
                        source_revision=source.source_revision,
                        owner_scope_type=scope_type,
                        owner_scope_id=scope_id,
                        classification=scope_type,
                    ),
                )
                for source in payload.source_page
            )
            items = [
                {
                    "state": result.state,
                    "knowledge_resource_id": result.knowledge_resource_id,
                    "security_label_id": result.security_label_id,
                    "projection_revision_id": (
                        result.projection_revision_id
                    ),
                    "authz_revision": result.authz_revision,
                }
                for result in revoke_results
            ]
            first = items[0]
            return {
                "intake_id": payload.intake_id,
                "knowledge_resource_id": first["knowledge_resource_id"],
                "security_label_id": first["security_label_id"],
                "projection_revision_id": first["projection_revision_id"],
                "authz_revision": first["authz_revision"],
                "state": (
                    "revoked"
                    if any(item["state"] == "revoked" for item in items)
                    else "reused"
                ),
                "indexed_chunks": 0,
                "source_count": len(items),
                "items": items,
            }
        compiler = self._load_compiler(
            descriptor.compiler_backend,
            descriptor.capability_code,
        )
        compiled = compiler(payload)
        if inspect.isawaitable(compiled):
            compiled = await compiled
        if isinstance(compiled, ProjectionCompilerOutput):
            compiled_outputs = (compiled,)
        elif isinstance(compiled, ProjectionCompilerPageOutput):
            compiled_outputs = compiled.outputs
        else:
            raise TypeError("knowledge_projection_compiler_output_invalid")
        if len(compiled_outputs) != len(payload.source_page):
            raise ValueError(
                "knowledge_projection_compiler_page_count_mismatch"
            )
        by_source_id = {
            item.identity.source_id: item for item in compiled_outputs
        }
        if len(by_source_id) != len(compiled_outputs):
            raise ValueError(
                "knowledge_projection_compiler_source_duplicate"
            )
        ordered_outputs = tuple(
            by_source_id.get(source.source_instance_id)
            for source in payload.source_page
        )
        if any(item is None for item in ordered_outputs):
            raise ValueError(
                "knowledge_projection_compiler_source_missing"
            )
        results = []
        for source, compiled_output in zip(
            payload.source_page,
            ordered_outputs,
        ):
            assert compiled_output is not None
            self._validate_output(
                payload,
                compiled_output,
                source=source,
            )
            results.append(
                facade.project_retrievable(
                    access_context=context,
                    identity=compiled_output.identity,
                    payload=compiled_output.projection,
                    documents=compiled_output.documents,
                    acl_mutation=compiled_output.acl_mutation,
                )
            )
        result = results[0]
        items = [
            {
                "state": item.state,
                "knowledge_resource_id": item.knowledge_resource_id,
                "security_label_id": item.security_label_id,
                "projection_revision_id": item.projection_revision_id,
                "authz_revision": item.authz_revision,
                "indexed_chunks": item.indexed_chunks,
            }
            for item in results
        ]
        return {
            "state": (
                "degraded"
                if any(item.state == "degraded" for item in results)
                else (
                    "reused"
                    if all(item.state == "reused" for item in results)
                    else "indexed"
                )
            ),
            "intake_id": payload.intake_id,
            "knowledge_resource_id": result.knowledge_resource_id,
            "security_label_id": result.security_label_id,
            "projection_revision_id": result.projection_revision_id,
            "authz_revision": result.authz_revision,
            "indexed_chunks": sum(item.indexed_chunks for item in results),
            "source_count": len(items),
            "items": items,
        }

    @staticmethod
    def _load_compiler(
        backend: str,
        capability_code: str,
    ) -> ProjectionCompiler:
        module_name, separator, attribute = backend.partition(":")
        if (
            separator != ":"
            or not module_name.startswith(
                f"capabilities.{capability_code}."
            )
            or not attribute
        ):
            raise ValueError("knowledge_projection_compiler_backend_forbidden")
        module = importlib.import_module(module_name)
        compiler = getattr(module, attribute, None)
        if not callable(compiler):
            raise LookupError("knowledge_projection_compiler_not_callable")
        return compiler

    @staticmethod
    def _validate_output(
        task: KnowledgeProjectionTaskPayload,
        compiled: ProjectionCompilerOutput,
        *,
        source=None,
    ) -> None:
        source = source or task.source
        identity = compiled.identity
        if (
            identity.tenant_id != task.tenant_id
            or identity.owner_capability_code
            != task.descriptor.capability_code
            or identity.source_kind != source.source_kind
            or identity.source_id != source.source_instance_id
            or identity.source_ref != source.source_ref
            or identity.source_revision != source.source_revision
            or identity.owner_scope_type
            != ("group" if task.group_id else "workspace")
            or identity.owner_scope_id
            != (task.group_id or task.workspace_id)
            or compiled.projection.content_hash
            != source.content_hash
        ):
            raise ValueError("knowledge_projection_compiler_identity_mismatch")


def create_knowledge_project_source_tool() -> KnowledgeProjectSourceTool:
    return KnowledgeProjectSourceTool()


__all__ = [
    "KnowledgeProjectSourceTool",
    "ProjectionCompiler",
    "ProjectionCompilerOutput",
    "ProjectionCompilerPageOutput",
    "create_knowledge_project_source_tool",
]
