# Timeline Panel File Plan

Source file:
- `/Users/shock/Projects_local/workspace/mindscape-ai-local-core/web-console/src/app/workspaces/components/TimelinePanel.tsx`

Parent plan:
- `/Users/shock/Projects_local/workspace/mindscape-ai-local-core/.agent/plans/large-file-modularization/local-core-implementation-modularization-plan-2026-03-23.md`

## Phase 1: Evidence Collection

- `:68` defines `TimelineItem`.
- `:95` defines `ExecutionSession`.
- `:112` defines `ExecutionStep`.
- `:123` starts the props and export surface.
- `:133` exports `TimelinePanel`.
- Earlier import audit confirmed active mounts from the execution page, `DefaultLeftSidebar.tsx`, and `WorkspaceLeftSidebar.tsx`.
- Caller grep shows active compatibility usage: `TimelinePanel` = 11.

## Phase 1.5: Historical Regression Analysis

- Commits `42d1799`, `f8ae209`, `98b7a9f`, and `1d34970` expanded UI behavior and reuse without creating a smaller timeline package.
- The file became a shared multipurpose panel for several shells.

## Phase 2: Problem Definition + Severity Scoring

1. **Shared-panel overload**: types, projections, UI sections, and interaction logic live in one large component. Severity 4, Detection 4, Priority 16.
2. **Reuse fragility**: multiple import sites depend on one large default export. Severity 4, Detection 3, Priority 12.
3. **No focused component test coverage**: current safety net is mostly type-check/lint. Severity 3, Detection 4, Priority 12.

## Phase 3: Assumption Verification

- Assumption: the current path must stay stable as a shell export.
  Verification: the panel is mounted from multiple current UI surfaces.
- Assumption: direct timeline tests are absent today.
  Verification: current `web-console` scripts expose `npm run type-check` and `npm run lint`; no dedicated `TimelinePanel` test file was found.

## Phase 3.5: Pre-Mortem

- Shared props drift between execution page and left sidebar callers.
- Timeline item formatting changes after extraction.
- One of the current mount points loses `use client` compatibility.

## Phase 4: Plan Writing

Target package:
- `web-console/src/app/workspaces/components/timeline/`

Modules to create:
- `TimelinePanel.tsx`
- `TimelineList.tsx`
- `TimelineItemRow.tsx`
- `ExecutionSummary.tsx`
- `useTimelineState.ts`
- `types.ts`
- `formatters.ts`
- `streamAdapters.ts`

Implementation order:
1. Extract shared types and formatting helpers.
2. Extract any SSE/projection adapters used to shape timeline entries.
3. Extract state logic into `useTimelineState.ts`.
4. Split list/row/summary presentational pieces.
5. Leave the old file as a thin shell re-exporting the new default component.

Do-not-miss checklist:
- [ ] shared types moved
- [ ] formatters moved
- [ ] state logic moved
- [ ] list/row/summary components split
- [ ] old import path preserved

## Phase 5: Citation Audit

Re-verify before coding:
- `:68`
- `:95`
- `:112`
- `:123`
- `:133`

## Phase 6: Validation SOP

```bash
cd /Users/shock/Projects_local/workspace/mindscape-ai-local-core/web-console
npm run type-check
npm run lint
```

## Phase 7: Evaluation & Automated Testing SOP

- Add at least one dedicated timeline rendering test before removing inline projections.
- Verify all three current import sites still compile against the same default export.
