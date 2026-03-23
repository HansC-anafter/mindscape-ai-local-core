# Models And Quota Panel File Plan

Source file:
- `/Users/shock/Projects_local/workspace/mindscape-ai-local-core/web-console/src/app/settings/components/panels/ModelsAndQuotaPanel.tsx`

Parent plan:
- `/Users/shock/Projects_local/workspace/mindscape-ai-local-core/.agent/plans/large-file-modularization/local-core-implementation-modularization-plan-2026-03-23.md`

## Phase 1: Evidence Collection

- `:12` defines `ModelItem`.
- `:28` defines `ModelConfigCardData`.
- `:39` starts the filter/type cluster.
- `:57` exports `ModelsAndQuotaPanel`.
- `:530` starts the `LOCAL_PROVIDERS` cluster.
- The file imports `CliApiKeysSection` at line 10 and renders it again later in the panel.
- Caller grep shows active compatibility usage: `ModelsAndQuotaPanel` = 5.

## Phase 1.5: Historical Regression Analysis

- Commits `d243d82`, `cae8ad7`, `044cf6b`, and `51b0a0d` expanded model, provider, and quota UI behavior in this one panel.
- The panel kept absorbing sections instead of delegating to smaller stateful components.

## Phase 2: Problem Definition + Severity Scoring

1. **Panel-of-panels overload**: filters, provider sections, model cards, quota behavior, and embedded runtime-key UI live together. Severity 4, Detection 4, Priority 16.
2. **Cross-file coupling**: this panel already embeds another large component, which complicates refactor order. Severity 4, Detection 4, Priority 16.
3. **No focused component tests**: compile/lint are the main current safety net. Severity 3, Detection 4, Priority 12.

## Phase 3: Assumption Verification

- Assumption: this file should become a shell export with extracted sections underneath.
  Verification: it is an active mounted settings panel with a stable import surface.
- Assumption: the `CliApiKeysSection` dependency must be handled explicitly in refactor order.
  Verification: the file imports and renders that section directly today.

## Phase 3.5: Pre-Mortem

- Extracting `CliApiKeysSection` second creates a circular dependency or duplicated state.
- Model filters drift from provider sections.
- `LOCAL_PROVIDERS` or quota logic changes during breakup without test coverage.

## Phase 4: Plan Writing

Target package:
- `web-console/src/app/settings/components/model-quota/`

Modules to create:
- `ModelsAndQuotaPanel.tsx`
- `ModelFilters.tsx`
- `ModelCardGrid.tsx`
- `ProviderSections.tsx`
- `QuotaSummary.tsx`
- `useModelQuotaState.ts`
- `types.ts`
- `providerConstants.ts`

Implementation order:
1. Extract shared types and provider constants.
2. Extract filter and quota-state logic into `useModelQuotaState.ts`.
3. Split filter, model-card, and provider-section components.
4. Keep `CliApiKeysSection` extraction in sync so the shell dependency stays clean.
5. Leave the old file as a thin shell re-exporting the new default component.

Do-not-miss checklist:
- [ ] shared types moved
- [ ] provider constants moved
- [ ] filter/quota state moved
- [ ] panel sections split
- [ ] `CliApiKeysSection` dependency order handled
- [ ] old import path preserved

## Phase 5: Citation Audit

Re-verify before coding:
- `:12`
- `:28`
- `:39`
- `:57`
- `:530`

## Phase 6: Validation SOP

```bash
cd /Users/shock/Projects_local/workspace/mindscape-ai-local-core/web-console
npm run type-check
npm run lint
```

## Phase 7: Evaluation & Automated Testing SOP

- Add at least one dedicated panel test for filter behavior before moving state logic.
- Sequence this refactor with `CliApiKeysSection` so only one side owns the shared runtime/quota state.
