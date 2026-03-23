# Intent Analyzer File Plan

Source file:
- `/Users/shock/Projects_local/workspace/mindscape-ai-local-core/backend/app/services/playbook/intent_analyzer.py`

Parent plan:
- `/Users/shock/Projects_local/workspace/mindscape-ai-local-core/.agent/plans/large-file-modularization/local-core-implementation-modularization-plan-2026-03-23.md`

## Phase 1: Evidence Collection

- `:49` defines `ToolSlotIntentAnalyzer`.
- `:68` starts `analyze_and_filter_tools()`.
- `:148` starts `_should_escalate()`.
- `:253` starts `_is_ambiguous_message()`.
- `:974` starts `_parse_llm_response()`.
- `:1039` starts `get_tool_slot_intent_analyzer()`.
- `:1064` starts `get_intent_analyzer()`.
- Caller grep shows active compatibility usage: `ToolSlotIntentAnalyzer` = 0, `intent_analyzer` = 18.

## Phase 1.5: Historical Regression Analysis

- Commits `56d0caa`, `b071785`, `e11041d`, and `7d821d8` added async DB, confidence thresholds, routing logic, and analyzer factory behavior here.
- Factory and parsing logic kept expanding in the same file.

## Phase 2: Problem Definition + Severity Scoring

1. **Decision-stack overload**: ambiguity checks, escalation rules, LLM response parsing, and factory wiring live together. Severity 4, Detection 4, Priority 16.
2. **Factory coupling**: creation helpers and analysis logic are not separated. Severity 4, Detection 4, Priority 16.
3. **Parser fragility**: LLM-response parsing changes can silently affect routing. Severity 4, Detection 3, Priority 12.

## Phase 3: Assumption Verification

- Assumption: callers rely on factory functions and module path more than private helpers.
  Verification: grep shows module-path usage is much broader than direct class-name usage.
- Assumption: strategy tests exist.
  Verification: `/Users/shock/Projects_local/workspace/mindscape-ai-local-core/backend/tests/test_playbook_invocation_strategy.py` and `/Users/shock/Projects_local/workspace/mindscape-ai-local-core/backend/tests/test_real_conversation.py` exist.

## Phase 3.5: Pre-Mortem

- Ambiguity and escalation rules diverge after extraction.
- Factory returns misconfigured analyzers.
- Parser normalization changes without focused tests.

## Phase 4: Plan Writing

Target package:
- `backend/app/services/playbook/intent/`

Modules to create:
- `analyzer.py`
- `ambiguity_rules.py`
- `escalation_rules.py`
- `response_parser.py`
- `factory.py`

Implementation order:
1. Extract parser normalization into `response_parser.py`.
2. Extract ambiguity and escalation rules into pure modules.
3. Move main analyzer class to `analyzer.py`.
4. Move factory functions to `factory.py`.
5. Leave the old file as a facade exporting the same factories and analyzer.

Do-not-miss checklist:
- [ ] parser moved
- [ ] ambiguity rules moved
- [ ] escalation rules moved
- [ ] factory functions moved
- [ ] old module path preserved

## Phase 5: Citation Audit

Re-verify before coding:
- `:49`
- `:68`
- `:148`
- `:253`
- `:974`
- `:1039`
- `:1064`

## Phase 6: Validation SOP

```bash
pytest backend/tests/test_playbook_invocation_strategy.py \
  backend/tests/test_real_conversation.py
```

## Phase 7: Evaluation & Automated Testing SOP

- Add focused parser contract tests before moving `_parse_llm_response()`.
- Add a factory import contract test if module-path callers are sensitive.
