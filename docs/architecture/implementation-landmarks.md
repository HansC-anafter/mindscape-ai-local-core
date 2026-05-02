# Implementation Landmarks

This page lists public source landmarks for the released Local Core architecture documents. It is a code navigation aid, not an exhaustive API reference.

The list intentionally focuses on Local Core host contracts and shared runtime surfaces. It excludes ignored paths, generated runtime artifacts, capability-owned service internals, internal reports, work logs, and private validation material.

## Route Registration

Core route registration starts in:

- `backend/app/app_bootstrap/routes.py`

Workspace-scoped route aggregation starts in:

- `backend/app/routes/core/workspace/__init__.py`

These files are the safest entry points for understanding which route families are mounted by the local backend.

## Runtime Environments

Runtime environment and runtime mediation landmarks:

- `backend/app/models/runtime_environment.py`
- `backend/app/routes/core/runtime_environments.py`
- `backend/app/routes/core/runtime_oauth.py`
- `backend/app/routes/core/runtime_proxy.py`
- `backend/app/routes/core/workspace/runtime.py`
- `backend/app/routes/core/workspace_runtime_config.py`
- `backend/app/routes/core/settings_extensions.py`
- `backend/app/services/runtime_auth_service.py`
- `backend/app/services/runtime_contract_registry.py`
- `backend/app/services/runtime_route_registration.py`

These files cover local runtime registry behavior, runtime OAuth, runtime proxying, workspace runtime configuration, settings extension discovery, and runtime route wiring.

## Addressable Object Layer

AOL host contract landmarks:

- `backend/app/models/object_runtime.py`
- `backend/app/routes/core/workspace/object_runtime.py`
- `backend/app/services/object_catalog_registry.py`
- `backend/app/services/object_index_sync_service.py`
- `backend/app/services/object_meeting_attachment_service.py`
- `backend/app/services/stores/object_instance_registry_store.py`
- `backend/app/services/stores/object_relation_registry_store.py`
- `web-console/src/lib/addressable-object-layer.ts`
- `web-console/src/components/capabilities/AddressableObjectHostShell.tsx`
- `web-console/src/components/capabilities/meeting-workbench/AOLMeetingBottomShell.tsx`

These files cover object identity transport, workspace object routes, catalog discovery, index sync, meeting attachment, relation storage, and frontend host-shell integration.

## Memory Fabric

Governed memory landmarks:

- `backend/app/models/memory_contract.py`
- `backend/app/services/stores/postgres/memory_item_store.py`
- `backend/app/services/stores/postgres/memory_version_store.py`
- `backend/app/services/stores/postgres/memory_evidence_link_store.py`
- `backend/app/services/stores/postgres/memory_edge_store.py`
- `backend/app/services/stores/postgres/memory_writeback_run_store.py`
- `backend/app/services/memory/writeback/meeting_memory_writeback_orchestrator.py`
- `backend/app/services/governance/lens_policy_memory_selector.py`
- `backend/app/services/governance/memory_packet_compiler.py`
- `backend/app/services/governance/memory_impact_graph_read_model.py`
- `backend/app/routes/core/workspace_governance.py`

World memory landmarks:

- `backend/app/system_capabilities/world_memory_core/schema/world_memory_packet.py`
- `backend/app/system_capabilities/world_memory_core/schema/world_state_snapshot.py`
- `backend/app/system_capabilities/world_memory_core/schema/world_card_projection.py`
- `backend/app/system_capabilities/world_memory_core/services/world_state_adapter.py`
- `backend/app/system_capabilities/world_memory_core/services/world_card_projection_compiler.py`

These files separate canonical governed memory, evidence-linked writeback, selected memory packets, memory impact review, and bounded world-state projection.

## Meeting, TaskIR, and Dispatch

Meeting orchestration and TaskIR landmarks:

- `backend/app/models/task_ir.py`
- `backend/app/models/meeting_session.py`
- `backend/app/routes/meeting_sessions.py`
- `backend/app/routes/core/handoff_bundles.py`
- `backend/app/routes/core/workspace/meeting_graph.py`
- `backend/app/services/conversation/pipeline_meeting.py`
- `backend/app/services/orchestration/meeting/engine.py`
- `backend/app/services/orchestration/meeting/_ir_compiler.py`
- `backend/app/services/orchestration/meeting/_dispatch_pipeline.py`
- `backend/app/services/orchestration/meeting/dispatch_gate.py`
- `backend/app/services/orchestration/meeting/dispatch_policy_gate.py`
- `backend/app/services/orchestration/meeting/meeting_supervisor.py`
- `backend/app/services/orchestration/dispatch_orchestrator.py`
- `backend/app/services/stores/task_ir_store.py`
- `backend/app/services/stores/postgres/task_ir_store.py`

These files cover meeting session lifecycle, handoff compile intake, meeting graph access, TaskIR compilation, dispatch gating, policy gating, DAG dispatch, supervisor hooks, and TaskIR persistence.

## Tool Retrieval and Resource Bindings

Tool and resource binding landmarks:

- `backend/app/models/workspace_resource_binding.py`
- `backend/app/routes/core/workspace_resource_bindings.py`
- `backend/app/routes/core/tools/filtered.py`
- `backend/app/routes/core/tools/rag_search.py`
- `backend/app/services/tool_registry.py`
- `backend/app/services/tool_embedding_service.py`
- `backend/app/services/tool_rag.py`
- `backend/app/services/tool_rag_refresh.py`
- `backend/app/services/stores/workspace_resource_binding_store.py`
- `backend/app/services/playbook_registry.py`

These files cover local tool discovery, filtered tool views, RAG-backed tool search, embedding refresh, workspace resource bindings, and playbook registry lookup.

## Capability Hosting Boundary

Capability host landmarks:

- `backend/app/services/capability_api_loader.py`
- `backend/app/app_bootstrap/capability_activation_middleware.py`
- `backend/app/routes/core/capability_packs.py`
- `backend/app/routes/core/capability_suites.py`
- `backend/app/routes/core/capability_install.py`
- `backend/app/services/pack_capability_index.py`
- `backend/app/services/manifest_validator.py`
- `backend/app/services/install_integrity.py`

These files are host-boundary landmarks only. Public Local Core documentation must still avoid per-capability backend service code, frontend UI implementation details, capability-specific schemas, migrations, prompt material, and generated runtime artifacts.

## Reading Rule

Use these landmarks to verify public architecture boundaries against the repository. If a candidate document depends on capability-owned internals, ignored paths, generated artifacts, private validation material, or working-tree files that are not part of the released repository state, keep that material out of public docs.
