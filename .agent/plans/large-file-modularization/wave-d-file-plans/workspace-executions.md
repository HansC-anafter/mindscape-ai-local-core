# Workspace Executions Feature File Plan

Source file:
- `/Users/shock/Projects_local/workspace/mindscape-ai-local-core/backend/features/workspace/executions.py`

Parent plan:
- `/Users/shock/Projects_local/workspace/mindscape-ai-local-core/.agent/plans/large-file-modularization/local-core-implementation-modularization-plan-2026-03-23.md`

## Phase 1: Evidence Collection

- `:45` defines `ExecutionStreamEvent`.
- `:49` starts `execution_update()`.
- `:62` starts `step_update()`.
- `:94` starts `collaboration_update()`.
- `:125` starts `execution_chat()`.
- `:1101` defines `ExecutionChatRequest`.
- `:1114` starts `post_execution_chat()`.
- `:1253` starts `handle_execution_response()`.
- Caller grep shows active compatibility usage: `workspace.executions` = 20.

## Phase 1.5: Historical Regression Analysis

- Commits `42d1799`, `d2fcc7a`, `1cbd0e5`, and `bb84f52` added SSE/chat/runtime-profile behavior into the same feature file.
- Stream events, read endpoints, and write/chat behavior kept accreting in one route module.

## Phase 2: Problem Definition + Severity Scoring

1. **Transport overload**: SSE event types, chat endpoints, response mapping, and feature routes live together. Severity 5, Detection 4, Priority 20.
2. **Read/write boundary leakage**: stream event projection and POST chat behavior are mixed. Severity 4, Detection 4, Priority 16.
3. **Runtime-profile coupling**: execution chat behavior can regress alongside unrelated route changes. Severity 4, Detection 3, Priority 12.

## Phase 3: Assumption Verification

- Assumption: the feature route can become a package while preserving the old import path.
  Verification: imports are path-sensitive, but event families and handlers are separable.
- Assumption: workspace execution tests exist.
  Verification: `/Users/shock/Projects_local/workspace/mindscape-ai-local-core/backend/tests/test_execution_chat_agent_service.py`, `/Users/shock/Projects_local/workspace/mindscape-ai-local-core/backend/tests/test_workspace_runtime_profile.py`, `/Users/shock/Projects_local/workspace/mindscape-ai-local-core/backend/tests/test_runtime_profile_e2e.py`, `/Users/shock/Projects_local/workspace/mindscape-ai-local-core/backend/tests/test_running_server_routes.py`, and `/Users/shock/Projects_local/workspace/mindscape-ai-local-core/backend/tests/test_workspace_instruction_chat_merge.py` exist.

## Phase 3.5: Pre-Mortem

- SSE event names or payloads change during extraction.
- Chat response mapping diverges from stream event projection.
- Client-facing runtime-profile behavior regresses because handlers are split without shared contracts.

## Phase 4: Plan Writing

Target package:
- `backend/features/workspace/executions/`

Modules to create:
- `router.py`
- `schemas.py`
- `stream_events.py`
- `sse_transport.py`
- `chat_handlers.py`
- `response_mapper.py`

Implementation order:
1. Extract event DTOs and schemas.
2. Extract SSE/stream helpers.
3. Extract execution chat handlers and request parsing.
4. Extract response mapping helpers.
5. Leave the old file as a facade re-exporting the router object.

Do-not-miss checklist:
- [ ] event DTOs moved
- [ ] SSE helpers moved
- [ ] execution chat handlers moved
- [ ] response mapper moved
- [ ] router export preserved
- [ ] old import path preserved

## Phase 5: Citation Audit

Re-verify before coding:
- `:45`
- `:49`
- `:62`
- `:94`
- `:125`
- `:1101`
- `:1114`
- `:1253`

## Phase 6: Validation SOP

```bash
pytest backend/tests/test_execution_chat_agent_service.py \
  backend/tests/test_workspace_runtime_profile.py \
  backend/tests/test_runtime_profile_e2e.py \
  backend/tests/test_running_server_routes.py \
  backend/tests/test_workspace_instruction_chat_merge.py
```

## Phase 7: Evaluation & Automated Testing SOP

- Add event-payload contract tests before moving `ExecutionStreamEvent` and stream helpers.
- Add a router import contract test if the feature package path becomes a facade.
