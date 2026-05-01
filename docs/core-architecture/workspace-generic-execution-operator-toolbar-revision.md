# Workspace Generic Execution Operator Toolbar Runtime Correction

Status: Proposed  
Scope: Corrective implementation details for execution-chat/operator entry after runtime-boundary audit. This document supersedes the earlier pack-launched entry draft as the active guidance.

## Phase 1: Evidence Collection

### Evidence

- **E1. Local-Core is the runtime host; the capability source workspace is authoring/packaging only.** The red-line guide states that `mindscape-ai-local-core` is only a runtime environment, and capability source must be developed in the canonical capability source workspace, packaged, then installed into Local-Core. (`../docs-internal/DEVELOPER_GUIDE_MINDSCAPE_AI.md:146-155`)
- **E2. Installed capability UI paths inside Local-Core are not source-of-truth.** Deploy rules explicitly forbid direct edits under `local-core/web-console/src/app/capabilities/<pack>/` and require capability UI edits in the canonical capability source workspace. (`deploy-pack` skill rules)
- **E3. Capability installation happens through Local-Core, and installed UI files are copied into Local-Core web-console.** The installation guide says packaging happens in the source workspace, installation happens through the Local-Core API, and installed UI files land in `web-console/src/app/capabilities/{capability_code}/components/`. (`../docs-internal/CAPABILITY_INSTALLATION_GUIDE.md:83-166`, `../docs-internal/CAPABILITY_INSTALLATION_GUIDE.md:211-236`)
- **E4. The source workspace is not a UI install/runtime path.** The installation guide says Pack UI installation and runtime loading happen in Local-Core, not in the source workspace. (`../docs-internal/CAPABILITY_INSTALLATION_GUIDE.md:142-166`)
- **E5. Execution runtime ownership is explicitly Local-Core / semantic-hub, not the source workspace.** The boundary guides define execution as `local-core runtime` or `semantic-hub runtime`; the source workspace is not a runtime host. (`../docs-internal/DEVELOPER_GUIDE_MINDSCAPE_AI.md`, `../docs-internal/CAPABILITY_INSTALLATION_GUIDE.md`)
- **E6. Local-Core already owns the workspace shell runtime surface.** Workspace pages mount under `web-console/src/app/workspaces/[workspaceId]/...`, and the shared layout currently hosts workspace-level navigation/event plumbing. (`web-console/src/app/workspaces/[workspaceId]/layout.tsx:1-108`)
- **E7. Local-Core already owns the canonical execution detail surface.** The dedicated execution page lives under `/workspaces/{workspaceId}/executions/{executionId}` and already hosts the execution inspector/chat surface. (`web-console/src/app/workspaces/[workspaceId]/executions/[executionId]/page.tsx:1-120`)
- **E8. Local-Core already owns the execution-chat backend/runtime contract.** The backend exposes `/api/v1/workspaces/{workspace_id}/executions/{execution_id}/chat`, resolves execution-chat config locally, and routes agent turns through the Local-Core execution-chat service. (`backend/features/workspace/executions.py:31-34`, `backend/features/workspace/executions.py:1049-1264`)
- **E9. The failed implementation path directly modified Local-Core installed capability UI and added a Local-Core launcher/helper path.** The audit found `ExecutionContextMenu`, `execution-navigation.ts`, workspace-layout launcher handling, and pack-local IG installed-path entries. (`web-console/src/components/execution/ExecutionContextMenu.tsx`, `web-console/src/lib/execution-navigation.ts`, `web-console/src/app/workspaces/[workspaceId]/layout.tsx:38-90`, `web-console/src/app/capabilities/ig/...`)

## Phase 1.5: Historical Regression Analysis

### H1. The first failure came from editing the easiest UI files, not the correct ownership layer.

- The initial pass added operator actions in Local-Core installed capability UI because those files were immediately available.
- That repeated the exact violation forbidden by the deploy/install rules: editing the installed copy instead of the canonical pack source. (E1, E2, E3, E9)

### H2. The second failure came from over-correcting source-of-truth into runtime ownership.

- After noticing the installed-path violation, the correction attempt incorrectly claimed that the source workspace should own the workspace-generic toolbar runtime.
- That contradicted the red-line runtime split: execution runtime lives in Local-Core / semantic-hub, while the source workspace remains authoring/packaging only. (E4, E5, E6, E7, E8)

### H3. The stable precedent was already present: execution chat is a Local-Core execution surface.

- Long before the launcher experiments, Local-Core already had the execution detail page and execution-chat backend/runtime.
- So the structurally correct correction is to keep execution chat/operator runtime in Local-Core, while fixing source-of-truth and launch ownership drift around it. (E6, E7, E8)

## Phase 2: Problem Definition + Severity Scoring

1. **[P1] Installed-path source-of-truth violation**: execution-chat launcher affordances were added in Local-Core capability-installed UI paths, which are explicitly not authoring surfaces. (E1, E2, E3, E9)
2. **[P2] Runtime-boundary drift**: the correction path then incorrectly treated the cloud repo as if it should host the workspace-generic operator runtime. (E4, E5)
3. **[P3] Interaction-model drift**: operator entry was implemented as pack-local buttons/context menus rather than a workspace-generic execution surface. (E6, E7, E9)
4. **[P4] Correction-scoping risk**: fixing P1 and P2 must not dislodge the already-correct Local-Core execution page/chat runtime. (E6, E7, E8)
5. **[P5] Overlay confusion risk**: `x_platform.local_core.execution_chat` can be misread as a launch contract even though it only affects execution-chat behavior after the surface is opened. (E8)

| Problem | Severity | Detection | Priority |
|---------|----------|-----------|----------|
| P1 Installed-path source-of-truth violation | 5 | 5 | 25 |
| P2 Runtime-boundary drift | 5 | 4 | 20 |
| P3 Interaction-model drift | 4 | 4 | 16 |
| P4 Correction-scoping risk | 4 | 3 | 12 |
| P5 Overlay confusion risk | 3 | 4 | 12 |

## Phase 3: Assumption Verification (CoVe)

| Assumption | Verification Question | Answer |
|---|---|---|
| Promoting a source-only repo into workspace runtime ownership is acceptable. | Do any mandatory guides allow a source-only repo to own installed pack/workspace runtime UI? | No. The mandatory guides say the capability source/code workspace is authoring-only, while installation/runtime happens in Local-Core only. (E1, E3, E4, E5) |
| Local-Core already has a valid runtime host for execution operator surfaces. | Is there an existing workspace shell and canonical execution surface in Local-Core? | Yes. `layout.tsx` hosts workspace-level runtime wiring, and the dedicated execution page already exists. (E6, E7) |
| Execution chat backend/runtime must be preserved in Local-Core. | Is execution chat already exposed as a Local-Core execution-scoped API and agent loop? | Yes. The execution-chat endpoints and agent-turn path are already Local-Core owned. (E8) |
| Pack-local buttons are required for execution chat launch. | Does the current system require pack-specific chat backends or pack-specific execution surfaces? | No. Execution chat is already execution-scoped and canonicalized in Local-Core. Pack-local launchers are a UX choice, not a runtime requirement. (E7, E8) |
| Editing `local-core/web-console/src/app/capabilities/<pack>/` is acceptable for this work. | What do the deploy/install rules say about those paths? | They are installed copies and must not be treated as authoring surfaces. (E2, E3) |

## Phase 3.5: Pre-Mortem

### Failure Mode 1: The next implementation again edits installed capability UI paths inside Local-Core.

- Evidence ruling it out: the deploy/install rules explicitly forbid that. (E2, E3)
- Mitigation in this plan: all pack-source edits stay in the canonical source workspace; Local-Core work only targets core workspace shell / execution surfaces. (Resolves P1)

### Failure Mode 2: The correction over-rotates and moves workspace execution operator runtime into the source workspace.

- Evidence ruling it out: the runtime split and install chain explicitly keep runtime in Local-Core / semantic-hub. (E1, E3, E4, E5)
- Mitigation in this plan: define generic operator toolbar/runtime as Local-Core workspace-shell responsibility only. (Resolves P2, P4)

### Failure Mode 3: `x_platform.local_core.execution_chat` gets reused as the generic launch permission model.

- Evidence ruling it out: none, unless the docs say otherwise.
- Mitigation in this plan: make the overlay rule explicit and repeat it in the implementation section. (Resolves P5)

## Phase 4: Revised Implementation Plan

### I1. Publish the boundary correction in authoritative docs
Resolves Problem #2, #4.

- Keep the operative implementation-details document in Local-Core, because the runtime host and workspace shell both live there.
- Update Local-Core architecture indexing so the superseded pack-launched draft is no longer treated as current guidance.

Verified insertion points:

- `docs/core-architecture/README.md`
- `docs/core-architecture/workbench-execution-chat-entry.md`

### I2. Re-anchor runtime ownership in Local-Core workspace shell
Resolves Problem #2, #3, #4.

The workspace-generic execution operator toolbar, if implemented, must be treated as a **Local-Core runtime surface**.

Verified runtime host surfaces:

- workspace shell: `web-console/src/app/workspaces/[workspaceId]/layout.tsx`
- canonical execution surface: `web-console/src/app/workspaces/[workspaceId]/executions/[executionId]/page.tsx`
- execution-chat backend/runtime: `backend/features/workspace/executions.py`

Concrete replacement logic:

1. Do **not** nominate the source workspace as the runtime owner.
2. Do **not** place the generic toolbar inside pack-local installed UI copies.
3. Define the toolbar, selection state, and launch semantics against the Local-Core workspace shell and canonical execution surface.

### I3. Re-anchor source-of-truth boundaries without moving runtime
Resolves Problem #1, #2.

The correct split is:

1. pack-specific UI source is authored in the canonical capability source workspace
2. packaged as `.mindpack`
3. installed into Local-Core
4. rendered by Local-Core runtime

This means:

- the source workspace remains the authoring/packaging home for pack UI source
- Local-Core remains the runtime host for installed pack UI and workspace-generic operator surfaces

Concrete replacement logic:

- direct edits under `local-core/web-console/src/app/capabilities/<pack>/` remain prohibited
- any generic operator surface must target Local-Core core UI, not pack-installed copies
- the source workspace must not be described as the runtime owner of the toolbar

### I4. The workspace-generic launch contract inherits the core execution contract
Resolves Problem #3, #4.

Any generic operator action must resolve from the existing core execution identity, not from a pack-private model.

Minimum inherited contract:

- `workspace_id`
- `execution_id`
- optional `parent_execution_id`
- `trace_id`
- execution status / lineage metadata

Concrete launch rule:

1. a surface may expose execution context or selection state
2. the workspace-generic operator surface uses `workspace_id + execution_id`
3. Local-Core opens/focuses the existing execution surface
4. execution chat, resend, rerun, and inspection continue to use Local-Core governance/runtime

### I5. `x_platform.local_core.execution_chat` stays an overlay only
Resolves Problem #5.

Carry forward this exact rule:

`x_platform.local_core.execution_chat` 只是把這些能力接進 local-core 的 execution chat 操作面。

It is:

- **not** the source of execution capability
- **not** the reason a workbench may surface operator actions
- **not** a replacement for the core execution contract

It only decides execution-chat behavior after the execution surface is already opened.

### I6. Cleanup is a separate approved follow-up
Resolves Problem #1, #3.

This document does not revert code. The cleanup task should run separately and remove or quarantine:

- Local-Core installed-path pack launcher experiments
- Local-Core experimental launcher/helper paths that encoded the rejected interaction model
- any remaining doc text that treats pack-local launchers or source-workspace runtime ownership as desired architecture

## Phase 5: Citation Audit (Critical Checks)

The most critical citations were re-verified for this revision:

- Local-Core runtime-only warning: `../docs-internal/DEVELOPER_GUIDE_MINDSCAPE_AI.md:146-155`
- Deploy boundary: `deploy-pack` skill rules
- Source package / Local-Core install chain: `../docs-internal/CAPABILITY_INSTALLATION_GUIDE.md:83-166`
- Installed UI file target in Local-Core: `../docs-internal/CAPABILITY_INSTALLATION_GUIDE.md:211-236`
- Execution plane split: Local-Core boundary guides
- Local-Core workspace shell: `web-console/src/app/workspaces/[workspaceId]/layout.tsx:1-108`
- Local-Core canonical execution page: `web-console/src/app/workspaces/[workspaceId]/executions/[executionId]/page.tsx:1-120`
- Local-Core execution chat runtime: `backend/features/workspace/executions.py:1049-1264`

## Phase 6: Validation SOP

### Scenario A: Runtime-boundary validation
Problems covered: P2, P4

Steps:

1. Re-read the install/runtime split:

```bash
nl -ba /Users/shock/Projects_local/workspace/mindscape-ai-local-core/docs-internal/CAPABILITY_INSTALLATION_GUIDE.md | sed -n '83,166p'
```

2. Re-read the Local-Core runtime-only warning:

```bash
nl -ba /Users/shock/Projects_local/workspace/mindscape-ai-local-core/docs-internal/DEVELOPER_GUIDE_MINDSCAPE_AI.md | sed -n '146,155p'
```

Pass:

- the docs clearly state that Local-Core is the runtime host
- no document claims the source workspace hosts the workspace-generic toolbar runtime

Fail:

- any document still says the source workspace owns the runtime toolbar/shell

### Scenario B: Workspace-shell host validation
Problems covered: P3, P4

Steps:

1. Verify the existing Local-Core workspace shell:

```bash
nl -ba '/Users/shock/Projects_local/workspace/mindscape-ai-local-core/web-console/src/app/workspaces/[workspaceId]/layout.tsx' | sed -n '1,108p'
```

2. Verify the existing Local-Core canonical execution page:

```bash
nl -ba '/Users/shock/Projects_local/workspace/mindscape-ai-local-core/web-console/src/app/workspaces/[workspaceId]/executions/[executionId]/page.tsx' | sed -n '1,120p'
```

3. Verify the execution-chat backend/runtime:

```bash
rg -n "executions/\\{execution_id\\}/chat|post_execution_chat|handle_execution_chat_agent_turn|resolve_execution_chat_config" \
  /Users/shock/Projects_local/workspace/mindscape-ai-local-core/backend/features/workspace/executions.py
```

Pass:

- Local-Core already has a valid workspace-shell/runtime host for execution operator surfaces
- the plan layers on top of those surfaces instead of re-homing them

Fail:

- the plan requires a new source-workspace runtime host for the same execution surface

### Scenario C: Installed-path boundary validation
Problems covered: P1, P3

Steps:

1. Re-read the deploy/install red line from the approved deploy workflow.

2. Audit the current experimental code scope:

```bash
rg -n "dispatchOpenExecutionChat|ExecutionContextMenu|open-execution-chat" \
  /Users/shock/Projects_local/workspace/mindscape-ai-local-core/web-console/src/app/capabilities \
  /Users/shock/Projects_local/workspace/mindscape-ai-local-core/web-console/src/lib \
  /Users/shock/Projects_local/workspace/mindscape-ai-local-core/web-console/src/components
```

Pass:

- installed capability UI edits are treated as cleanup debt, not valid implementation precedent

Fail:

- a new plan or PR treats those installed-path edits as the approved way forward

## Phase 7: Evaluation & Automated Testing SOP

### Test Set T1: Runtime-boundary doc guard
Prevents: P2, P4

Add a grep-based doc guard that fails if architecture docs contain phrases equivalent to:

- `source-only repo promoted into workspace-generic runtime ownership`
- `source-only repo promoted into Pack UI install/runtime ownership`

### Test Set T2: Installed-path authoring guard
Prevents: P1

Add a static audit that fails if new feature work directly targets:

- `local-core/web-console/src/app/capabilities/<pack>/`

unless the change is explicitly marked as installer/runtime infrastructure rather than pack feature authoring.

### Test Set T3: Overlay-semantics guard
Prevents: P5

Add a docs/code audit that checks `x_platform.local_core.execution_chat` is only described as:

- behavior override after execution chat is opened

and never as:

- the permission source for launchable operator actions
