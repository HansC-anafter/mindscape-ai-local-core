# Pending Tasks Panel File Plan

Source file:
- `/Users/shock/Projects_local/workspace/mindscape-ai-local-core/web-console/src/app/workspaces/components/PendingTasksPanel.tsx`

Parent plan:
- `/Users/shock/Projects_local/workspace/mindscape-ai-local-core/.agent/plans/large-file-modularization/local-core-implementation-modularization-plan-2026-03-23.md`

## Phase 1: Evidence Collection

- `:13` defines the inline `PlaybookIntentSubtitle` subcomponent.
- `:177` defines the `Task` interface cluster.
- `:197` defines `PendingTasksPanelProps`.
- `:211` exports `PendingTasksPanel`.
- Earlier file inspection shows inline animation CSS, domain types, fetch/update logic, and filtering all live in this one client component.
- Caller grep shows active compatibility usage: `PendingTasksPanel` = 9.
- Active mount confirmed from `/Users/shock/Projects_local/workspace/mindscape-ai-local-core/web-console/src/components/workspace/DecisionPanel.tsx:6`.

## Phase 1.5: Historical Regression Analysis

- Commits `b264811`, `98b7a9f`, `c3921d7`, and `1d34970` added UI sections and behavior without extracting hooks or child components.
- The growth pattern is repeated feature accretion into one panel file.

## Phase 2: Problem Definition + Severity Scoring

1. **Client-component overload**: subcomponents, styles, domain types, fetch/update logic, and rendering live together. Severity 4, Detection 4, Priority 16.
2. **State/render coupling**: panel state and presentational sections are hard-wired. Severity 4, Detection 4, Priority 16.
3. **No focused component tests**: refactor safety relies mostly on type-check and lint today. Severity 3, Detection 4, Priority 12.

## Phase 3: Assumption Verification

- Assumption: the current file path should remain as a thin compatibility shell.
  Verification: the panel is actively imported by another workspace component.
- Assumption: direct component tests are limited.
  Verification: current `web-console` scripts expose `npm run type-check` and `npm run lint`; no dedicated `PendingTasksPanel` test file was found.

## Phase 3.5: Pre-Mortem

- `use client` boundaries move and break hooks.
- Filtering behavior drifts after state extraction.
- Inline animation or subtitle rendering gets dropped during breakup.

## Phase 4: Plan Writing

Target package:
- `web-console/src/app/workspaces/components/pending-tasks/`

Modules to create:
- `PendingTasksPanel.tsx`
- `PendingTasksList.tsx`
- `PendingTaskCard.tsx`
- `PlaybookIntentSubtitle.tsx`
- `usePendingTasksState.ts`
- `types.ts`
- `animations.ts`

Implementation order:
1. Extract shared types and inline subtitle component.
2. Extract stateful fetch/update/filter logic into `usePendingTasksState.ts`.
3. Split list/card rendering components.
4. Move animation/style helpers out of the main shell.
5. Leave the old file as a thin client shell re-exporting the new default component.

Do-not-miss checklist:
- [ ] `use client` boundary preserved
- [ ] task types moved
- [ ] fetch/update/filter logic moved
- [ ] list/card components split
- [ ] animation helpers moved
- [ ] old import path preserved

## Phase 5: Citation Audit

Re-verify before coding:
- `:13`
- `:177`
- `:197`
- `:211`

## Phase 6: Validation SOP

```bash
cd /Users/shock/Projects_local/workspace/mindscape-ai-local-core/web-console
npm run type-check
npm run lint
```

## Phase 7: Evaluation & Automated Testing SOP

- Add the first dedicated `PendingTasksPanel` rendering/state test before deleting old inline helpers.
- Keep the old file as a shell until DecisionPanel imports are verified unchanged.
