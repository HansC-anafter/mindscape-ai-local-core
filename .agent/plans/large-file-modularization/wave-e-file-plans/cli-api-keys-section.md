# CLI API Keys Section File Plan

Source file:
- `/Users/shock/Projects_local/workspace/mindscape-ai-local-core/web-console/src/app/workspaces/[workspaceId]/components/CliApiKeysSection.tsx`

Parent plan:
- `/Users/shock/Projects_local/workspace/mindscape-ai-local-core/.agent/plans/large-file-modularization/local-core-implementation-modularization-plan-2026-03-23.md`

## Phase 1: Evidence Collection

- `:7` defines `PoolAccount`.
- `:18` defines `ExecutorSpec`.
- `:88` defines `AgentTab`.
- `:189` starts `formatTimeRemaining()`.
- `:202` defines the props surface.
- `:206` exports `CliApiKeysSection`.
- Active mounts were confirmed from `RuntimeSettingsModal.tsx` and `ModelsAndQuotaPanel.tsx`.
- Caller grep shows active compatibility usage: `CliApiKeysSection` = 8.

## Phase 1.5: Historical Regression Analysis

- Commits `465cd18`, `66bfb81`, `ff09899`, and `64debdd` added more quota/runtime UI behavior to this one section.
- The file became both runtime account state manager and presentational panel.

## Phase 2: Problem Definition + Severity Scoring

1. **Section overload**: account types, tab state, time formatting, runtime actions, and rendering live together. Severity 4, Detection 4, Priority 16.
2. **Cross-panel coupling**: the section is mounted inside another large panel while also serving a modal. Severity 4, Detection 3, Priority 12.
3. **No direct component tests**: current safety relies on compile/lint. Severity 3, Detection 4, Priority 12.

## Phase 3: Assumption Verification

- Assumption: this file path should remain stable as a shell export during migration.
  Verification: the component is mounted from multiple active shells.
- Assumption: direct component tests are absent today.
  Verification: current `web-console` scripts expose `npm run type-check` and `npm run lint`; no dedicated `CliApiKeysSection` test file was found.

## Phase 3.5: Pre-Mortem

- Time/expiration formatting changes after extraction.
- Agent-tab selection logic drifts from rendered sections.
- Dependency on `ModelsAndQuotaPanel` creates a circular UI split.

## Phase 4: Plan Writing

Target package:
- `web-console/src/app/workspaces/[workspaceId]/components/runtime-api-keys/`

Modules to create:
- `CliApiKeysSection.tsx`
- `AgentTabs.tsx`
- `QuotaSummary.tsx`
- `ApiKeyList.tsx`
- `useRuntimeApiKeysState.ts`
- `types.ts`
- `time.ts`

Implementation order:
1. Extract shared types and time-format helpers.
2. Extract stateful runtime account/quota logic into `useRuntimeApiKeysState.ts`.
3. Split tab and list/summary rendering components.
4. Leave the old file as a thin shell re-exporting the new default component.

Do-not-miss checklist:
- [ ] shared types moved
- [ ] time helper moved
- [ ] runtime state logic moved
- [ ] tab/list/summary components split
- [ ] old import path preserved

## Phase 5: Citation Audit

Re-verify before coding:
- `:7`
- `:18`
- `:88`
- `:189`
- `:202`
- `:206`

## Phase 6: Validation SOP

```bash
cd /Users/shock/Projects_local/workspace/mindscape-ai-local-core/web-console
npm run type-check
npm run lint
```

## Phase 7: Evaluation & Automated Testing SOP

- Add a focused test for `formatTimeRemaining()` and tab switching before removing inline helpers.
- Extract this section before or together with `ModelsAndQuotaPanel` to avoid a circular UI migration.
