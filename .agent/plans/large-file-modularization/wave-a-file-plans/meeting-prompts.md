# Meeting Prompts File Plan

Source file:
- `/Users/shock/Projects_local/workspace/mindscape-ai-local-core/backend/app/services/orchestration/meeting/_prompts.py`

Parent plan:
- `/Users/shock/Projects_local/workspace/mindscape-ai-local-core/.agent/plans/large-file-modularization/local-core-wave-a-execution-orchestration-implementation-plan-2026-03-23.md`

## Phase 1: Evidence Collection

- `:41` defines `MeetingPromptsMixin`.
- `:71` starts tool inventory construction.
- `:654` starts turn prompt construction.
- `:1019` starts system message assembly.
- Caller grep shows active compatibility usage: `MeetingPromptsMixin` = 2, `meeting._prompts` = 1.

## Phase 1.5: Historical Regression Analysis

- Commits `42d1799`, `1afb88d`, `3a92d10`, `a370e6c`, `aa9c6a3` added more context sources, tool discovery, persona detail, and optimization rules here.

## Phase 2: Problem Definition + Severity Scoring

1. **Prompt builder overload**: workspace context, tool inventory, project/lens context, turn prompt, and system message live in one mixin. Severity 4, Detection 4, Priority 16.
2. **Context-source entanglement**: unrelated context builders are coupled through one file. Severity 4, Detection 4, Priority 16.
3. **Compatibility risk**: mixin method names still need to work for `MeetingEngine`. Severity 4, Detection 3, Priority 12.

## Phase 3: Assumption Verification

- Assumption: the mixin can delegate to extracted modules.
  Verification: caller surface is narrow and method-oriented.
- Assumption: prompt tests exist.
  Verification: `/Users/shock/Projects_local/workspace/mindscape-ai-local-core/backend/tests/services/orchestration/test_meeting_prompt_injection.py` exists.

## Phase 3.5: Pre-Mortem

- Prompt composition order changes silently.
- Tool inventory loses one context source.
- Old mixin keeps half the logic and does not actually shrink.

## Phase 4: Plan Writing

Target package:
- `backend/app/services/orchestration/meeting/prompts/`

Modules to create:
- `workspace_context.py`
- `tool_inventory.py`
- `project_context.py`
- `turn_prompt.py`
- `minutes.py`
- `system_message.py`

Implementation order:
1. Extract workspace and tool context builders.
2. Extract project/lens/decision context builders.
3. Extract turn prompt helpers.
4. Extract minutes/history and system message assembly.
5. Leave `_prompts.py` as delegating mixin only.

Do-not-miss checklist:
- [ ] workspace context extracted
- [ ] tool inventory extracted
- [ ] project/lens/decision context extracted
- [ ] turn prompt extracted
- [ ] system message extracted
- [ ] old mixin preserved

## Phase 5: Citation Audit

Re-verify before coding:
- `:41`
- `:71`
- `:654`
- `:1019`

## Phase 6: Validation SOP

```bash
pytest backend/tests/services/orchestration/test_meeting_prompt_injection.py \
  backend/tests/services/orchestration/test_meeting_asset_map.py \
  backend/tests/test_agent_mode_prompt_verification.py
```

## Phase 7: Evaluation & Automated Testing SOP

- Add a prompt snapshot/contract test if extracted builders change assembly order.
