# Workbench Execution Chat Entry

Superseded: this draft captured a now-rejected pack-launched entry model.  
Use [Workspace Generic Execution Operator Toolbar Revision](./workspace-generic-execution-operator-toolbar-revision.md) as the active implementation guidance.

Status: Historical  
Scope: Local-Core architecture-managed implementation details for exposing execution-scoped chat as a generic operator surface from any workspace-mounted pack workbench.

## Why This Exists

The target UX is:

1. the user is inside any pack workbench surface,
2. that surface already belongs to a workspace,
3. the user is acting on a concrete execution,
4. a context-menu action such as "Open Execution Chat" should open the same execution-scoped chat surface with discussion + agent/tool calling.

The key architectural point is that this is **not** a pack-specific chat stack. It is a **Local-Core execution operator surface** that pack workbenches can launch when they already hold `workspace_id` and `execution_id`.

## Evidence

- **E1. Pack workbench routes are already workspace-mounted.** Capability and workbench routes live under `/workspaces/[workspaceId]/...`, including capability pages, brand workbenches, course workbenches, and execution pages. (`web-console/src/app/workspaces/[workspaceId]/capabilities/[capabilityCode]/page.tsx`, `web-console/src/app/workspaces/[workspaceId]/brand/page.tsx`, `web-console/src/app/workspaces/[workspaceId]/yogacoach/course-workbench/page.tsx`, `web-console/src/app/workspaces/[workspaceId]/executions/[executionId]/page.tsx`)
- **E2. The existing workbench/sidebar surfaces are already workspace-scoped.** `WorkspaceRightSidebar` and `MindscapeAIWorkbench` both take `workspaceId` as a required prop. (`web-console/src/app/workspaces/[workspaceId]/components/WorkspaceRightSidebar.tsx:20-36`, `web-console/src/components/MindscapeAIWorkbench.tsx:49-64`)
- **E3. Frontend execution state already carries both execution and workspace identity.** `WorkspaceDataContext` models `ExecutionSession` with `execution_id` and `workspace_id`, and maps task rows into that shape when loading workspace executions. (`web-console/src/contexts/WorkspaceDataContext.tsx:69-82`, `web-console/src/contexts/WorkspaceDataContext.tsx:407-421`)
- **E4. The dedicated execution surface already exists as a stable route.** The canonical route is `/workspaces/{workspaceId}/executions/{executionId}`, and workspace layout is the correct shell owner for execution-surface launch handling across all workspace-mounted pages. (`web-console/src/app/workspaces/[workspaceId]/layout.tsx`, `web-console/src/app/workspaces/[workspaceId]/executions/[executionId]/page.tsx`)
- **E5. Execution chat itself is already execution-scoped.** The execution inspector renders `ExecutionChatWrapper` / `ExecutionChatPanel` against a concrete `executionId` and `workspaceId`. (`web-console/src/app/workspaces/components/ExecutionInspector.tsx:329-339`, `web-console/src/app/workspaces/components/execution-inspector/ExecutionChatWrapper.tsx:10-40`)
- **E6. The backend chat endpoint is execution-scoped, not pack-scoped.** Execution chat is handled under `/api/v1/workspaces/{workspace_id}/executions/{execution_id}/chat`. (`backend/features/workspace/executions.py`)
- **E7. Local-Core already has a generic execution-chat agent loop with execution-specific tools.** The runtime path is centralized in `handle_execution_chat_agent_turn(...)`, `ExecutionChatToolCatalog`, and the execution-chat config resolver. (`backend/app/services/conversation/execution_chat_agent_service.py`, `backend/app/services/conversation/execution_chat_tool_catalog.py`, `backend/app/services/conversation/execution_chat_config.py`)

## Architectural Conclusion

### C0. All pack executions inherit the Core execution contract.

Any pack workbench that wants observability, rerun, retry, rollback, or execution chat must attach itself to the existing Local-Core execution identity and lifecycle contract rather than inventing a pack-private one.

Minimum inherited keys:

- `workspace_id`
- `execution_id`
- `parent_execution_id` when child / replay execution exists
- `trace_id`
- execution status lifecycle
- lineage / replay metadata

This means the workbench entry contract is always layered on top of a core-owned execution contract, not the other way around.

### C1. "Open Execution Chat" is a Local-Core surface contract.

Pack workbenches should not implement their own execution-side agent loop.  
They should only emit a generic launch intent with:

- `workspace_id`
- `execution_id`
- optional origin metadata such as `pack_code`, `surface_id`, `task_id`, `step_id`

From that point onward, Local-Core owns:

- execution detail loading,
- execution chat enablement,
- discussion vs agent selection,
- tool catalog selection,
- policy gating,
- resend / continue / inspection tools.

### C2. `x_platform.local_core.execution_chat` is an override surface, not the entry contract.

The execution-chat overlay decides how the Local-Core execution chat behaves once opened:

- enabled or disabled
- discussion vs agent
- tool groups
- loop budget
- discussion persona

`x_platform.local_core.execution_chat` 只是把這些能力接進 Local-Core 的 execution chat 操作面。

It does **not** define whether a pack workbench is allowed to launch execution chat in the first place.  
The launch contract comes from the existence of `workspace_id + execution_id`.

### C3. Rerun / rollback / retry remain part of execution governance, not workbench authoring.

Pack workbenches gain observability and operator actions by pointing at a governed execution.  
They do not need to author separate pack-local rerun semantics just to open the chat surface.

## Required Contract

### 1. Generic launch payload

Any workbench surface that wants to expose "Open Execution Chat" must be able to produce:

```ts
type OpenExecutionChatIntent = {
  workspaceId: string;
  executionId: string;
  originPackCode?: string;
  originSurfaceId?: string;
  taskId?: string;
  stepId?: string;
  openMode?: "route" | "sidebar";
};
```

Required fields:

- `workspaceId`
- `executionId`

Optional fields are observational only. They should be used for analytics, breadcrumbs, and future focused views, but must not be required for opening the chat.

### 2. Default routing behavior

Local-Core should define one canonical behavior:

1. if the caller is outside the execution page, navigate to  
   `/workspaces/{workspaceId}/executions/{executionId}`
2. once on that page, focus/open the existing execution chat panel
3. hydrate the chat surface from execution detail + playbook detail + execution-chat resolver

This keeps the operator surface singular.  
Do not create one chat route per pack.

### 3. Default enablement behavior

Default rule:

- if the execution exists, Local-Core may open the execution page
- if the resolved execution-chat config says chat is enabled, render chat immediately
- if no execution-chat override exists, Local-Core may still render the legacy discussion path when the playbook supports execution chat

Pack-specific overlay is only used to override behavior, for example:

- default to `agent`
- expose `execution_inspection`
- expose `execution_remote_control`

## Recommended UI Wiring

### Option A: route-first launch

Recommended as the default because it reuses the existing surface and URL model.

Workbench action:

```ts
window.dispatchEvent(
  new CustomEvent("open-execution-chat", {
    detail: {
      workspaceId,
      executionId,
      originPackCode,
      originSurfaceId,
      openMode: "route",
    },
  })
);
```

Local-Core shell behavior:

1. normalize event payload
2. navigate to `/workspaces/{workspaceId}/executions/{executionId}`
3. open/focus the right-side execution chat panel

### Option B: in-place sidebar launch

Allowed only when the current surface already embeds execution inspector semantics and can guarantee:

- the same `workspaceId`
- the same `executionId`
- the same execution data loaders
- the same policy-governed chat surface

If any of those are missing, fall back to route-first launch.

## Non-Goals

- A pack-specific chat backend per workbench
- A separate agent loop per pack
- Using `x_platform.local_core.execution_chat` as the only way to make execution chat reachable
- Requiring pack workbenches to reimplement resend / continue / remote-summary logic

## Implementation Notes

### Phase 1: standardize launch event

Add a dedicated Local-Core UI event such as `open-execution-chat`.

Implemented binding:

- event names:
  - `open-execution-inspector`
  - `open-execution-chat`
- shared helper:
  - `web-console/src/lib/execution-navigation.ts`
- chat launch URL shape:
  - `/workspaces/{workspaceId}/executions/{executionId}?open=chat&chat_focus_token=<token>`
- shell handler owner:
  - `web-console/src/app/workspaces/[workspaceId]/layout.tsx`

### Phase 2: centralize route handling

The workspace shell should own the event handler, not each pack workbench.

Responsibilities:

- validate `workspaceId`
- validate `executionId`
- navigate to the canonical execution route
- pass origin metadata as optional UI state if needed

### Phase 3: focus the execution chat panel

Execution page should accept a focused subview such as:

- `open=chat`
- `chat_focus_token=<opaque token>`

Implemented binding:

- `web-console/src/app/workspaces/[workspaceId]/executions/[executionId]/page.tsx` reads the search params
- `ExecutionChatPanel` focuses its textarea when `focusToken` changes

This avoids relying on pack-specific side effects after navigation.

### Phase 4: keep execution-chat behavior local-core-managed

After launch, the existing Local-Core stack remains authoritative:

- `resolve_execution_chat_config(...)`
- `handle_execution_chat_agent_turn(...)`
- `ExecutionChatToolCatalog`
- policy / approval / remote-step tools

## Recommended Rule Set

1. Any workspace-mounted pack workbench may show "Open Execution Chat" if it has both `workspace_id` and `execution_id`.
2. Every such entry inherits the core execution contract first; no pack-private execution identity model is allowed.
3. The action must call a generic Local-Core launch contract, not a pack-private route.
4. The canonical destination remains the execution page.
5. `x_platform.local_core.execution_chat` is used to shape behavior after launch, not to define the launch contract itself.
6. Rerun / retry / rollback stay in execution governance and are surfaced through execution chat tools, not duplicated inside pack workbenches.

## Current Local-Core Contract

Thin callers should use the shared launcher rather than dispatching raw stringly-typed events:

```ts
import { dispatchOpenExecutionChat } from '@/lib/execution-navigation';

dispatchOpenExecutionChat({
  workspaceId,
  executionId,
  originPackCode,
  originSurfaceId,
});
```

Equivalent route resolution is owned by Local-Core and must remain canonical:

```txt
/workspaces/{workspaceId}/executions/{executionId}?open=chat&chat_focus_token=<token>
```

`x_platform.local_core.execution_chat` 只是把這些能力接進 Local-Core 的 execution chat 操作面。

Current adopter status:

- Local-Core workspace shell owns the launch contract.
- IG workbench execution surfaces are the first pack-level adopter:
  - run logs
  - active execution debug card
  - seed execution cards

## Immediate Next Step

Expand adoption in pack workbench surfaces:

1. replace raw `CustomEvent("open-execution-inspector")` callsites with shared launch helpers where appropriate
2. wire pack workbench context menus to `dispatchOpenExecutionChat(...)`
3. keep pack workbenches as thin callers that only provide `workspaceId + executionId`
