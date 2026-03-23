# Local Filesystem Manager Content File Plan

Source file:
- `/Users/shock/Projects_local/workspace/mindscape-ai-local-core/web-console/src/app/settings/components/wizards/LocalFilesystemManagerContent.tsx`

Parent plan:
- `/Users/shock/Projects_local/workspace/mindscape-ai-local-core/.agent/plans/large-file-modularization/local-core-implementation-modularization-plan-2026-03-23.md`

## Phase 1: Evidence Collection

- `:13` defines the props interface.
- `:57` defines `EmptyPathInputWithWorkspaceName`.
- `:149` exports `LocalFilesystemManagerContent`.
- Active mounts were confirmed from `LocalFilesystemManager.tsx` and `StoragePathConfigModal.tsx`.
- Caller grep shows active compatibility usage: `LocalFilesystemManagerContent` = 6.

## Phase 1.5: Historical Regression Analysis

- Commits `df493dd`, `ecdcbb1`, `1d34970`, and `6e24e93` expanded settings workflow behavior while keeping content, forms, and rendering in one file.
- The file became both wizard flow logic and visual composition layer.

## Phase 2: Problem Definition + Severity Scoring

1. **Wizard/content overload**: props, helper inputs, flow logic, and rendering live together. Severity 4, Detection 4, Priority 16.
2. **Modal/wizard reuse coupling**: the same large content component serves multiple shells. Severity 4, Detection 3, Priority 12.
3. **No direct component tests**: current safety is mostly compile/lint. Severity 3, Detection 4, Priority 12.

## Phase 3: Assumption Verification

- Assumption: the file path should stay as a shell export because multiple parents mount it.
  Verification: current imports come from both the settings wizard and storage-path modal.
- Assumption: direct component tests are absent.
  Verification: current `web-console` scripts expose `npm run type-check` and `npm run lint`; no dedicated `LocalFilesystemManagerContent` test file was found.

## Phase 3.5: Pre-Mortem

- Wizard-specific state bleeds into modal usage after extraction.
- Path validation behavior drifts.
- `use client` or form-hook boundaries break when helpers move.

## Phase 4: Plan Writing

Target package:
- `web-console/src/app/settings/components/local-filesystem/`

Modules to create:
- `LocalFilesystemManagerContent.tsx`
- `WorkspacePathSections.tsx`
- `PathInputRow.tsx`
- `EmptyPathInputWithWorkspaceName.tsx`
- `useLocalFilesystemState.ts`
- `schemas.ts`
- `adapters.ts`

Implementation order:
1. Extract helper input components and shared types.
2. Extract validation/adaptation helpers.
3. Extract stateful wizard logic into `useLocalFilesystemState.ts`.
4. Split shell sections by UI region.
5. Leave the old file as a thin shell re-exporting the new default component.

Do-not-miss checklist:
- [ ] props/types moved
- [ ] helper input component moved
- [ ] validation/adapters moved
- [ ] state logic moved
- [ ] old import path preserved

## Phase 5: Citation Audit

Re-verify before coding:
- `:13`
- `:57`
- `:149`

## Phase 6: Validation SOP

```bash
cd /Users/shock/Projects_local/workspace/mindscape-ai-local-core/web-console
npm run type-check
npm run lint
```

## Phase 7: Evaluation & Automated Testing SOP

- Add the first dedicated settings-component test before removing inline validation helpers.
- Verify both current parent shells still compile against the same default export.
