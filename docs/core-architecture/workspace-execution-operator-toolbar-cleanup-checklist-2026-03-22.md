# Workspace Execution Operator Toolbar Cleanup Checklist

Status: Executed  
Date: 2026-03-22  
Scope: Remove the rejected Local-Core launcher/context-menu experiment while preserving the canonical Local-Core execution runtime.

## Completed Cleanup

1. Removed the experimental launcher/helper path from Local-Core core UI:
   - deleted `web-console/src/lib/execution-navigation.ts`
   - deleted `web-console/src/lib/execution-navigation.spec.ts`
   - deleted `web-console/src/components/execution/ExecutionContextMenu.tsx`
   - removed the `ExecutionContextMenu` export from `web-console/src/components/execution/index.ts`

2. Removed workspace-shell event wiring that depended on the rejected custom event contract:
   - cleaned `web-console/src/app/workspaces/[workspaceId]/layout.tsx`

3. Removed execution-page query/focus plumbing that only existed for the rejected launcher path:
   - cleaned `web-console/src/app/workspaces/[workspaceId]/executions/[executionId]/page.tsx`
   - cleaned `web-console/src/app/workspaces/components/ExecutionChatPanel.tsx`

4. Replaced event-based execution-detail launching with direct canonical route navigation:
   - cleaned `web-console/src/app/workspaces/components/TimelinePanel.tsx`
   - cleaned `web-console/src/hooks/useCurrentExecution.ts`

5. Neutralized installed IG runtime-copy residues so Local-Core no longer imports deleted launcher helpers:
   - cleaned `web-console/src/app/capabilities/ig/components/workbench/components/WorkbenchExecutionPanel/components/RunLogCard.tsx`
   - cleaned `web-console/src/app/capabilities/ig/components/workbench/components/WorkbenchExecutionPanel/components/ExecutionDebugCard.tsx`
   - cleaned `web-console/src/app/capabilities/ig/components/modules/accounts/components/SeedCard.tsx`

## Intentionally Preserved

1. Local-Core execution chat backend/runtime remains unchanged:
   - canonical execution page
   - `/api/v1/workspaces/{workspace_id}/executions/{execution_id}/chat`
   - execution governance / resend / inspection surfaces

2. Historical architecture record remains preserved for audit:
   - `docs/core-architecture/workbench-execution-chat-entry.md`

## Remaining Boundary Rules

1. New pack feature work must not target `local-core/web-console/src/app/capabilities/<pack>/`.
2. Pack source authoring remains in `mindscape-ai-cloud/capabilities/<pack>/`.
3. If future workspace-generic execution operator UI is introduced, it must be defined against Local-Core workspace/runtime surfaces, not pack-installed UI copies and not cloud runtime ownership.
