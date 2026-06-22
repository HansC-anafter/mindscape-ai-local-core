# Implementation Landmarks

This page lists public source landmarks for the released Local Core architecture documents. It is a code navigation aid for the stable host contracts described in this documentation set.

The list focuses on Local Core host contracts and shared runtime surfaces. Owner-managed capability code, generated runtime artifacts, and operational records stay in their owning documentation sets.

## Route Registration

Core route registration starts in:

- `backend/app/app_bootstrap/routes.py`

Workspace-scoped route aggregation starts in:

- `backend/app/routes/core/workspace/__init__.py`

These files are the safest entry points for understanding local backend host-surface registration.

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
- `backend/app/routes/host_runtime_sessions/rest_endpoints.py`
- `backend/app/routes/host_runtime_sessions/ws_endpoints.py`
- `backend/app/services/host_runtime_sessions/bridge_registry.py`
- `backend/app/services/host_runtime_sessions/session_store.py`

These files cover local runtime registry behavior, runtime access mediation, workspace runtime configuration, host runtime sessions, bridge registration, settings extension discovery, and host-surface registration.

## Host Resource and Queue Control

Host resource and local capacity landmarks:

- `backend/app/routes/core/host_resources.py`
- `backend/app/services/host_resources/lane_registry.py`
- `backend/app/services/host_resources/queue_utilization.py`
- `backend/app/services/host_resources/queue_utilization_response.py`
- `backend/app/services/host_resources/queue_backlog_aggregates.py`
- `backend/app/services/host_resources/workspace_allocations.py`
- `backend/app/services/host_resources/route_reservation_service.py`
- `backend/app/services/host_resources/runner_claim_modes.py`
- `backend/app/services/host_resources/runner_spillover_control.py`
- `backend/app/services/runner_topology/routing.py`
- `backend/app/services/runner_topology/default_local_browser.py`

These files cover host resource lanes, queue utilization projections, workspace allocation decisions, route intent preview, route reservations, runner claim gates, spillover control, and task-to-runner routing.

## Addressable Object Layer

AOL host contract landmarks:

- `backend/app/models/object_runtime/refs.py`
- `backend/app/models/object_runtime/catalog.py`
- `backend/app/models/object_runtime/instance_index.py`
- `backend/app/models/object_runtime/meeting.py`
- `backend/app/models/object_runtime/actions.py`
- `backend/app/models/object_runtime/materialization.py`
- `backend/app/models/object_runtime/graph.py`
- `backend/app/routes/core/workspace/object_runtime.py`
- `backend/app/services/object_catalog_registry.py`
- `backend/app/services/object_index_sync_service.py`
- `backend/app/services/object_meeting_attachment_service.py`
- `backend/app/services/stores/object_instance_registry_store.py`
- `backend/app/services/stores/object_relation_registry_store.py`
- `web-console/src/lib/addressable-object-layer.ts`
- `web-console/src/lib/object-reference-client.ts`
- `web-console/src/components/capabilities/AddressableObjectHostShell.tsx`
- `web-console/src/components/capabilities/meeting-workbench/AOLMeetingBottomShell.tsx`
- `web-console/src/components/object-references/InlineAolObjectRef.tsx`

These files cover object identity transport, workspace object host surfaces, catalog discovery, index sync, inline object preview, meeting attachment, relation storage, and frontend host-shell integration.

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

These files cover meeting session lifecycle, handoff intake boundaries, meeting graph access, TaskIR compilation, dispatch gating, policy gating, DAG dispatch, supervisor hooks, and TaskIR persistence.

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

These files cover local tool discovery, filtered tool surfaces, RAG-backed tool search, embedding refresh, workspace resource bindings, and playbook registry lookup.

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
- `web-console/src/app/workspaces/[workspaceId]/capability-ui-hosts/renderCapabilityUiHostPage.tsx`
- `web-console/src/app/workspaces/[workspaceId]/capability-ui-hosts/CapabilityHostRuntimeFrame.tsx`
- `web-console/src/app/workspaces/[workspaceId]/capability-ui-hosts/WorkspaceSurfaceShell.tsx`
- `web-console/src/components/capabilities/workbench/CapabilityWorkbenchResponsiveFrame.tsx`
- `web-console/src/components/capabilities/workbench/PackScopeToolRailHost.tsx`

These files are host-boundary landmarks. They cover capability package hosting, runtime UI host shells, workspace-scoped capability surfaces, shared tool rails, and responsive workbench framing. Per-capability backend service code, frontend UI implementation details, capability-specific schemas, migrations, assembly material, and generated runtime artifacts stay with the capability owner.

## Host Sidecar Services

Host sidecar service landmarks:

- `backend/app/routes/core/host_services.py`
- `backend/app/services/host_services/capture_relay_proxy.py`
- `device-node/src/mcp-server.ts`
- `device-node/src/capabilities/capture-relay-control.ts`

These files cover mediated access to selected host-side services. Public docs describe Local Core mediation and structured unavailable states. Device-specific setup and sidecar implementation internals stay with their owners.

## Reading Rule

Use these landmarks to verify public architecture boundaries against the repository. Candidate public documents should reference released repository files, stable host contracts, and owner boundaries that can be checked from the current source tree.
