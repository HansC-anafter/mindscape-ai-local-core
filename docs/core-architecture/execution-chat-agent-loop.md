# Execution Chat Agent Loop

Status: Draft  
Scope: Local-Core architecture-managed implementation details for turning execution-scoped chat from prompt-only discussion into an LLM + tool executor loop.

## Phase 1: Evidence Collection

### Evidence Items

- **E1. The right-side execution panel is already execution-scoped chat, not a separate tool UI.** `ExecutionChatWrapper` only renders the panel when `playbookMetadata.supports_execution_chat` is true, and it mounts `ExecutionChatPanel` against the current execution ID. (`web-console/src/app/workspaces/components/execution-inspector/ExecutionChatWrapper.tsx:24-40`)
- **E2. The frontend already treats execution chat as a stable backend surface.** `ExecutionChatPanel` polls execution status, loads `GET /api/v1/workspaces/{workspace_id}/executions/{execution_id}/chat`, and posts back to the same execution-scoped endpoint. (`web-console/src/app/workspaces/components/ExecutionChatPanel.tsx:100-167`, `web-console/src/app/workspaces/components/ExecutionChatPanel.tsx:194-240`)
- **E3. The current backend route has only two behaviors: hardcoded continue or plain chat reply.** `post_execution_chat()` stores the user event, computes `should_continue_execution`, and then either calls `PlaybookRunner.continue_playbook_execution(...)` or `generate_execution_chat_reply(...)`. (`backend/features/workspace/executions.py:1107-1302`)
- **E4. The current execution-chat service is prompt-only.** `build_execution_chat_prompt()` frames the assistant as a “Playbook Optimization Assistant” for improving `playbook.md` / `playbook.json`, and `generate_execution_chat_reply()` ultimately calls `generate_text(...)` with a single prompt string. (`backend/app/services/conversation/execution_chat_service.py:156-234`, `backend/app/services/conversation/execution_chat_service.py:263-327`)
- **E5. Execution-chat behavior must live behind a Local-Core-specific extension surface, not portable playbook core fields.** The current implementation path already uses `supports_execution_chat` / `discussion_agent` as legacy toggles, but the architecture-safe authoring surface is `x_platform.local_core.execution_chat`, with top-level execution-chat fields kept only as backward-compatibility fallback. (`backend/app/models/playbook_models/core.py`, `backend/app/services/conversation/execution_chat_config.py`)
- **E5a. The overlay is only an operator-surface binding, not the execution capability itself.** `x_platform.local_core.execution_chat` decides how Local-Core should expose execution chat once an execution has already inherited the core execution contract; it does not define rerun / retry / rollback semantics on its own. (`backend/app/services/conversation/execution_chat_config.py`)
- **E6. Local-Core already has a generic tool executor for builtin and capability tools.** `ToolExecutor.execute_tool()` resolves capability tools via the capability registry and builtin `MindscapeTool`s via the in-process tool registry. (`backend/app/shared/tool_executor.py:22-167`)
- **E7. Local-Core already has a reusable multi-turn tool-call loop.** `ToolExecutionLoop.execute_tool_loop()` parses tool-call JSON, runs tools iteratively, repairs formatting mistakes, and enforces loop budgets from the workspace runtime profile. (`backend/app/services/playbook/tool_execution/loop.py:174-363`)
- **E8. The existing playbook executor already wraps the loop with provider selection and tool execution.** `PlaybookToolExecutor` builds a `ToolExecutionLoop`, and `PlaybookRunner.continue_playbook_execution()` uses provider chat completion plus `self.tool_executor.execute_tool_loop(...)`. (`backend/app/services/playbook/tool_execution/executor.py:19-30`, `backend/app/services/playbook/tool_execution/executor.py:182-198`, `backend/app/services/playbook_runner.py:700-732`)
- **E9. Tool discovery surfaces already exist, but the generic filtered endpoint is MCP-oriented and readonly-biased.** `GET /api/v1/tools` merges discovered + capability tools, while `POST /api/v1/tools/filtered` always seeds a readonly-safe default set (`workspace_list_executions`, `workspace_get_execution`, `workspace_get_execution_steps`, `workspace_query_database`, `filesystem_*`). (`backend/app/routes/core/tools/base.py:227-309`, `backend/app/routes/core/tools/filtered.py:26-35`, `backend/app/routes/core/tools/filtered.py:121-224`)
- **E10. Existing workspace builtin tools are inspection-oriented only.** `workspace_tools.py` exposes `workspace_get_execution`, `workspace_get_execution_steps`, `workspace_list_executions`, `workspace_pick_relevant_execution`, and `workspace_query_database`; it does not expose execution-control tools such as continue or resend. (`backend/app/services/tools/workspace_tools.py:31-216`, `backend/app/services/tools/workspace_tools.py:369-785`)
- **E11. Generic execution-control operations already exist in Local-Core services/routes.** The workspace tasks API already supports `parent_execution_id` filtering and `POST /tasks/{task_id}/resend-remote-step`, and replay logic is implemented in `remote_step_resend_service.py`. (`backend/app/routes/core/workspace/tasks.py:343-477`, `backend/app/routes/core/workspace/tasks.py:755-792`, `backend/app/services/remote_step_resend_service.py:20-177`)
- **E12. Remote execution summary projection already exists and should be reused instead of rebuilt inside a new tool.** `build_remote_execution_summary()` and `project_execution_for_api()` already derive `remote_execution_summary`, lineage, replay, and target device metadata from task payloads. (`backend/app/services/task_execution_projection.py:18-73`)
- **E13. Runtime-profile controls already exist for tool allow/deny, explicit approval, loop budgets, and tool-chain length.** `ToolPolicy`, `ConfirmationPolicy`, and `LoopBudget` already define `allow_parallel_tool_calls`, `max_tool_call_chain`, `confirm_soft_write`, `confirm_external_write`, and `max_tool_calls`. (`backend/app/models/workspace_runtime_profile.py:110-210`)
- **E14. `PolicyGuard` only resolves policy info via `ToolRegistryService.get_tool(tool_id)`.** `ToolPolicyResolver.resolve_policy_info()` depends on `tool_registry.get_tool(tool_id)`, and `ToolRegistryService.get_tool()` only returns `self._tools.get(tool_id)`. (`backend/app/services/tool_policy_resolver.py:26-88`, `backend/app/services/tool_registry.py:985-987`)
- **E15. Builtin tools are available through `ToolListService` / `MindscapeTool` registration, not through `ToolRegistryService`.** `ToolListService._get_builtin_tools()` registers workspace/filesystem tools from the in-process registry, while `ToolRegistryService` loads only database-backed discovered tools into `_tools`. (`backend/app/services/tool_list_service.py:203-235`, `backend/app/services/tool_registry.py:84-174`)
- **E16. The current policy-enforcement path does not stop on “requires approval”.** `ToolPolicyEnforcer.enforce()` calls `PolicyGuard.check_tool_call(...)`, but when `policy_result.requires_approval` is true it only logs; it does not block or return a pending proposal. (`backend/app/services/playbook/tool_execution/policy.py:24-104`)

## Phase 1.5: Historical Regression Analysis

### H1. Execution chat was originally discussion-only, then patched with a single hardcoded action.

- Commit `854669b` added the `should_continue_execution` branch and the `PlaybookRunner.continue_playbook_execution(...)` fallback into `post_execution_chat()`. This fixed the specific regression where execution chat could not resume paused runs, but it solved only one action path and did not establish a generic tool-execution protocol for execution chat. (`git show 854669b -- backend/features/workspace/executions.py`)

### H2. Subsequent execution-chat changes improved reliability, not agent semantics.

- Commits `b70e02f`, `56d0caa`, and `21763ac` changed execution chat around `LocalDomainContext`, async safety, and timezone correctness. None of them changed the core behavior that execution chat is a prompt-only discussion path backed by `generate_text(...)`. (`git log -p -- backend/app/services/conversation/execution_chat_service.py backend/features/workspace/executions.py`)

### H3. A reusable tool-call loop was later extracted for playbook execution.

- Commit `643e19f` introduced `ToolExecutionLoop` as a standalone component with format repair, loop budgets, and retry logic. This provides a structurally better base than growing more hardcoded branches inside execution chat. (`git show 643e19f -- backend/app/services/playbook/tool_execution/loop.py`)

### Historical Conclusion

The current codebase has already demonstrated both failure modes we need to avoid:

1. adding one-off action branches to execution chat (`continue_playbook_execution`) and
2. keeping execution chat as a prompt-only discussion surface.

The new design must therefore:

1. preserve legacy discussion mode,
2. reuse the extracted tool-loop kernel instead of inventing another parser, and
3. introduce a real policy/approval boundary for action tools instead of adding more route-specific branches.

## Phase 2: Problem Definition + Severity Scoring

1. **[P1] Execution chat is still discussion-first rather than action-capable.** The backend prompt explicitly frames execution chat as playbook-analysis/revision assistance and routes non-paused messages through `generate_text(...)` only. (E3, E4)
2. **[P2] Execution actions are implemented as route-specific special cases instead of tool-discoverable capabilities.** `continue_playbook_execution` is hardcoded into the route, while resend/replay and remote summary live elsewhere. (E3, E11, H1)
3. **[P3] Builtin tools are not visible to the current policy resolver.** Execution-chat agent mode cannot safely depend on builtin workspace tools because `ToolPolicyResolver` only consults `ToolRegistryService`, while builtin tools are exposed through `ToolListService` / `MindscapeTool` registration. (E14, E15)
4. **[P4] The current tool policy path does not enforce approval semantics.** `requires_approval` is logged but not converted into a block, pause, or proposal, which is unacceptable for execution-chat action tools such as remote-step resend. (E13, E16)
5. **[P5] The existing workspace builtin tool set is missing execution-control tools and remote-debug helpers.** The agent can inspect executions but cannot natively list child replays, fetch remote summaries, continue execution, or resend a remote workflow-step child via tools. (E10, E11, E12)
6. **[P6] The generic filtered-tools endpoint is not a sufficient catalog for execution chat.** It is MCP-oriented, readonly-biased, and does not express execution-specific gating rules. (E9)
7. **[P7] Playbook execution infrastructure is reusable, but its conversation manager is SOP/playbook specific.** `PlaybookConversationManager` injects playbook SOP, slot info, and revision-oriented instructions; reusing it verbatim would pollute execution chat semantics. (E7, E8)

| Problem | Severity | Detection | Priority |
|---|---:|---:|---:|
| P3 Builtin tools bypass current policy resolver | 5 | 5 | 25 |
| P4 Approval semantics are logged, not enforced | 5 | 4 | 20 |
| P2 Route-specific action branches | 4 | 4 | 16 |
| P1 Discussion-only backend | 4 | 3 | 12 |
| P5 Missing execution-control tools | 4 | 3 | 12 |
| P6 Generic filtered-tools endpoint is a poor fit | 3 | 4 | 12 |
| P7 Playbook conversation manager is too specific | 3 | 3 | 9 |

## Phase 3: Assumption Verification (CoVe)

| Assumption | Verification Question | Answer |
|---|---|---|
| The existing right panel can stay on the same route/UI | Does the frontend already talk to an execution-scoped chat endpoint and gate itself by metadata? | Yes. The existing panel already posts to `/executions/{execution_id}/chat` and is enabled via `supports_execution_chat`. (E1, E2) |
| Local-Core already has a reusable tool loop | Is there an extracted loop with iterative tool execution and model re-entry? | Yes. `ToolExecutionLoop.execute_tool_loop()` already performs looped tool execution with retry/repair. (E7) |
| Execution chat can switch from `generate_text()` to provider chat completion | Is there an existing provider-manager path that already produces `provider.chat_completion(messages, ...)`? | Yes. `PlaybookRunner.continue_playbook_execution()` and `PlaybookLLMProviderManager` already use provider chat completion. (E8) |
| Action tools can reuse existing execution services | Do resend/continue operations already exist as service helpers and not only as UI code? | Yes. Continue lives in `PlaybookRunner.continue_playbook_execution()`, and resend lives in `remote_step_resend_service.py`. (E3, E11) |
| Current policy enforcement will safely gate write tools | Does `ToolPolicyEnforcer` block or pause when `requires_approval=True`? | No. It only logs approval requirements today. (E16) |
| Builtin tools can be policy-checked as-is | Does `ToolPolicyResolver` discover builtin workspace tools from the same source as `ToolExecutor`? | No. Resolver uses `ToolRegistryService`, while builtin tools come from `ToolListService` / `MindscapeTool`. (E14, E15) |

## Phase 3.5: Pre-Mortem

### Failure Mode 1: The agent can execute builtin tools without enforceable policy metadata.

- Why likely: builtin workspace tools are not in `ToolRegistryService`, but `PolicyGuard` resolves only from that store. (E14, E15)
- Mitigation: add a fallback synthesis path so policy resolution can build a `RegisteredTool`-equivalent view from builtin/capability tool catalogs before agent mode is enabled.

### Failure Mode 2: The agent silently performs write operations because approval is only logged.

- Why likely: `ToolPolicyEnforcer` logs `requires_approval` but does not block. (E16)
- Mitigation: add an execution-chat-specific approval mode that converts “requires approval” into a pending proposal / no-op result instead of actual execution.

### Failure Mode 3: Reusing playbook conversation machinery leaks SOP/revision semantics into execution chat.

- Why likely: `PlaybookConversationManager` is built around playbook SOP instructions and tool-slot prompt injection. (E7, E8)
- Mitigation: create a dedicated execution-chat conversation manager that exposes the same loop contract but uses execution-scoped prompt construction instead of playbook SOP framing.

## Phase 4: Implementation Details

### 4.0 Backup Warning

Validation for this feature will create execution-chat events and may resend remote child tasks. Take a database backup before implementation or manual verification:

```bash
docker compose exec -T postgres pg_dump -U mindscape -d mindscape_core > data/backups/mindscape_core_pre_test_$(date +%Y%m%d_%H%M%S).sql
```

### 4.1 Introduce an explicit execution-chat mode split

Resolves Problem #1, Problem #2, Problem #7

**Files**

- `backend/app/models/playbook_models/core.py`
- `backend/features/workspace/executions.py`
- `backend/app/services/conversation/execution_chat_service.py`

**Change**

Add an explicit Local-Core overlay for how execution chat should behave:

- `x_platform.local_core.execution_chat.enabled`
- `x_platform.local_core.execution_chat.mode`
- `x_platform.local_core.execution_chat.tool_groups`
- `x_platform.local_core.execution_chat.max_tool_iterations`
- `x_platform.local_core.execution_chat.discussion_agent`

Keep legacy top-level execution-chat fields only as fallback for existing playbooks. The resolver should treat `x_platform.local_core.execution_chat` as primary.

`x_platform.local_core.execution_chat` 只是把這些能力接進 Local-Core 的 execution chat 操作面。

**Precise replacement logic**

1. Add `x_platform` to `PlaybookMetadata` and introduce a resolver that normalizes `x_platform.local_core.execution_chat` into one stable config object with legacy fallback. (`backend/app/models/playbook_models/core.py`, `backend/app/services/conversation/execution_chat_config.py`)
2. In `post_execution_chat()`, replace the current binary branch:
   - `if chat_mode == "agent"` -> call new `handle_execution_chat_agent_turn(...)`
   - `elif should_continue_execution` -> preserve current hardcoded continue path for legacy discussion playbooks
   - `else` -> preserve current `generate_execution_chat_reply(...)`
3. Preserve the existing route and SSE contract so the frontend does not need a new surface, but project resolved execution-chat config back into the playbook detail payload for compatibility with the current execution inspector. (`backend/features/workspace/executions.py`, `backend/app/routes/core/playbook/queries.py`)

### 4.2 Split legacy discussion behavior from new agent behavior

Resolves Problem #1, Problem #7

**Files**

- `backend/app/services/conversation/execution_chat_service.py`
- `backend/app/services/conversation/execution_chat_agent_service.py` (new)
- `backend/app/services/conversation/execution_chat_conversation_manager.py` (new)

**Change**

Preserve the current prompt-only implementation as the legacy discussion path, but stop treating it as the only execution-chat backend.

**Precise replacement logic**

1. Keep `build_execution_chat_context()` as the shared context-builder baseline because it already assembles execution, step, and recent-chat context. (`backend/app/services/conversation/execution_chat_service.py:49-153`)
2. Rename or conceptually re-scope the existing `generate_execution_chat_reply()` path to “discussion mode” and leave its prompt semantics unchanged. (`backend/app/services/conversation/execution_chat_service.py:156-327`)
3. Add `ExecutionChatConversationManager` with the minimal loop contract required by `ToolExecutionLoop`:
   - `get_messages_for_llm()`
   - `parse_tool_calls_from_response()`
   - `add_assistant_message()`
   - `add_tool_call_results()`
4. Do **not** reuse `PlaybookConversationManager` directly because it injects SOP content, tool-slot instructions, and playbook-revision framing that are not appropriate for execution chat. (`backend/app/services/playbook/conversation_manager.py:20-120`, `backend/app/services/playbook/conversation_manager.py:160-260`)

### 4.3 Reuse the provider + tool-loop kernel, but not the discussion prompt path

Resolves Problem #1, Problem #7

**Files**

- `backend/app/services/playbook/llm_provider_manager.py`
- `backend/app/services/playbook/tool_execution/loop.py`
- `backend/app/services/playbook/tool_execution/executor.py`
- `backend/app/services/playbook_runner.py`
- `backend/app/services/conversation/execution_chat_agent_service.py` (new)

**Change**

The new execution-chat agent service should switch from `generate_text(prompt=...)` to message-based provider chat completion plus an iterative tool loop.

**Precise replacement logic**

1. Obtain the provider the same way playbook execution already does:
   - create / resolve LLM manager,
   - pick provider from settings,
   - call `provider.chat_completion(messages, model=...)`. (`backend/app/services/playbook/llm_provider_manager.py:14-62`, `backend/app/services/playbook_runner.py:700-710`)
2. Reuse `ToolExecutionLoop` for parse -> execute -> return-to-model iterations rather than inventing a second JSON tool-call parser. (`backend/app/services/playbook/tool_execution/loop.py:174-363`)
3. Reuse only the loop kernel and provider pattern. Do **not** blindly reuse `generate_text(...)`, because it has no notion of tool-call rounds. (`backend/app/services/conversation/execution_chat_service.py:285-291`)

### 4.4 Introduce an execution-chat-specific tool catalog

Resolves Problem #2, Problem #5, Problem #6

**Files**

- `backend/app/services/conversation/execution_chat_tool_catalog.py` (new)
- `backend/app/services/tool_list_service.py`
- `backend/app/services/tools/workspace_tools.py`

**Change**

Do not bind execution chat directly to `/api/v1/tools/filtered`, because that endpoint is designed for MCP gateway use and defaults to readonly-safe generic tools. (`backend/app/routes/core/tools/filtered.py:1-35`)

Add a dedicated internal catalog service that selects only execution-relevant tools for the current execution.

**Initial tool groups**

- `execution_inspection`
  - `workspace_get_execution`
  - `workspace_get_execution_steps`
  - `workspace_list_executions`
  - `workspace_list_child_executions` (new)
  - `workspace_get_execution_remote_summary` (new)
- `execution_control`
  - `workspace_continue_execution` (new)
- `execution_remote_control`
  - `workspace_resend_remote_step` (new)

**Precise replacement logic**

1. Build the catalog from `ToolListService.get_all_tools(...)`, then intersect with a small execution-chat allowlist instead of exposing the whole MCP tool surface. (`backend/app/services/tool_list_service.py:65-107`, `backend/app/services/tool_list_service.py:203-285`)
2. Use `playbook_metadata.execution_chat_tool_groups` to choose which groups are available for a given playbook.
3. Expose write-capable groups only when the current user message expresses an explicit action intent (for example: “繼續”, “重送”, “retry”, “resend”) so the right panel remains conversational but not silently auto-acting.

### 4.5 Fill the builtin execution-tool gap

Resolves Problem #5

**Files**

- `backend/app/services/tools/workspace_tools.py`
- `backend/app/services/task_execution_projection.py`
- `backend/app/services/remote_step_resend_service.py`
- `backend/app/services/playbook_runner.py`

**Change**

Add execution-focused builtin tools so the agent can inspect and operate on the current execution through the same local-core tool path as other tools.

**New tools**

1. `workspace_list_child_executions`
   - wraps existing task query path with `parent_execution_id`
   - returns projected execution rows with `remote_execution_summary`
2. `workspace_get_execution_remote_summary`
   - reuses `build_remote_execution_summary()` and grouped child lineage data instead of rebuilding remote-state JSON in the tool
3. `workspace_continue_execution`
   - wraps `PlaybookRunner.continue_playbook_execution(...)`
4. `workspace_resend_remote_step`
   - wraps `resend_remote_workflow_step_child_task(...)`

**Precise replacement logic**

1. Add the two new readonly tools next to existing execution inspection tools in `workspace_tools.py`, keeping them in the builtin workspace provider family. (`backend/app/services/tools/workspace_tools.py:31-216`)
2. Reuse `project_execution_for_api()` / `build_remote_execution_summary()` for summary shape so the center panel and agent see the same remote lineage fields. (`backend/app/services/task_execution_projection.py:18-73`)
3. Implement `workspace_resend_remote_step` by calling the existing resend service instead of re-implementing cloud dispatch. (`backend/app/services/remote_step_resend_service.py:69-177`)
4. Implement `workspace_continue_execution` by calling the existing playbook runner continuation path instead of duplicating state-restore logic. (`backend/app/services/playbook_runner.py:638-732`)

### 4.6 Fix policy resolution for builtin/capability tools

Resolves Problem #3

**Files**

- `backend/app/services/tool_policy_resolver.py`
- `backend/app/services/tool_list_service.py`
- `backend/app/models/tool_registry.py`

**Change**

`ToolPolicyResolver` must stop assuming that every tool lives in `ToolRegistryService`.

**Precise replacement logic**

1. Keep the current fast path: `ToolRegistryService.get_tool(tool_id)` first. (`backend/app/services/tool_policy_resolver.py:47-60`)
2. If the registry misses:
   - query `ToolListService.get_all_tools(...)`,
   - find the builtin/capability tool by ID,
   - synthesize a `RegisteredTool`-equivalent object with:
     - `tool_id`
     - `origin_capability_id`
     - `capability_code`
     - `danger_level`
     - `risk_class`
     - `side_effect_level`
3. For builtin workspace tools, define explicit mappings instead of relying on default `low -> readonly` inference:
   - inspection tools -> `risk_class="readonly"`
   - `workspace_continue_execution` -> `risk_class="soft_write"`
   - `workspace_resend_remote_step` -> `risk_class="external_write"`

This keeps policy evaluation inside Local-Core generic governance rather than bypassing it from execution chat.

### 4.7 Add a real approval boundary for action tools

Resolves Problem #4

**Files**

- `backend/app/services/playbook/tool_execution/policy.py`
- `backend/app/services/conversation/execution_chat_agent_service.py` (new)
- `backend/app/services/conversation/execution_chat_pending_actions_store.py` (new, lightweight)

**Change**

Do not reuse the current “log only” approval behavior for execution-chat action tools.

**Precise replacement logic**

1. Extend `ToolPolicyEnforcer.enforce()` with an optional mode:
   - `approval_mode="log"` for current playbook execution behavior
   - `approval_mode="return_pending"` for execution-chat agent mode
2. In `return_pending` mode:
   - if `policy_result.allowed is False` -> raise
   - if `policy_result.requires_approval is True` -> return the `PolicyCheckResult` instead of executing the tool
3. In execution-chat agent mode, convert a pending approval result into:
   - a persisted pending-action record (`proposal_id`, `tool_id`, `arguments`, `execution_id`, `workspace_id`)
   - an assistant `EXECUTION_CHAT` message asking for explicit confirmation
4. On a later user confirmation message, re-run the same tool call with the stored proposal instead of making the model reconstruct arguments from memory.

This is the key difference between “LLM has tools” and “LLM can silently perform execution-control actions”.

### 4.8 Keep the UI surface unchanged and observationally richer

Resolves Problem #2, Problem #6

**Files**

- No route changes required in the frontend for Phase 1
- Existing center-panel observability remains valid

**Change**

The existing right-side execution chat panel can remain the same because it already uses the correct execution-scoped route contract. The center-panel remote/replay surfaces remain useful for observability even after the right panel becomes tool-driven. (E1, E2)

No new hardcoded resend button is required for the first architecture slice.

## Phase 5: Citation Audit (Critical Insertions)

The following insertions were re-verified after drafting:

1. `backend/features/workspace/executions.py:1246-1300` still contains the exact current binary branch (`continue_playbook_execution` vs `generate_execution_chat_reply`) that this plan replaces in agent mode.
2. `backend/app/services/conversation/execution_chat_service.py:183-232` still frames the assistant as playbook-revision discussion, confirming that discussion mode and agent mode must be split.
3. `backend/app/services/tool_policy_resolver.py:47-60` and `backend/app/services/tool_registry.py:985-987` still confirm the current registry-only policy lookup.
4. `backend/app/services/playbook/tool_execution/policy.py:45-103` still confirms that `requires_approval` is logged but not enforced.
5. `backend/app/services/task_execution_projection.py:18-73` still confirms that remote-execution summary projection already exists and should be reused.

## Phase 6: Validation SOP

### Scenario A: Legacy discussion mode remains unchanged

**Steps**

1. Pick a playbook with `supports_execution_chat=true` and no `execution_chat_mode` override.
   Preferred authoring shape: `x_platform.local_core.execution_chat.enabled=true` with no `mode` override. Legacy top-level fields remain valid only for backward compatibility.
2. Open any execution detail page and send a discussion-style message in the right panel.
3. Watch SSE and inspect persisted `EXECUTION_CHAT` events.

**Pass**

- The assistant replies through the existing discussion path.
- No tool calls or pending-action proposals are emitted.
- Existing paused/waiting-confirmation legacy behavior remains unchanged.

**Fail**

- The route tries to enter tool mode for a legacy playbook.
- The assistant stops replying because provider chat completion was forced everywhere.

### Scenario B: Agent mode can perform readonly inspection

**Steps**

1. Enable `x_platform.local_core.execution_chat = { enabled: true, mode: "agent", tool_groups: ["execution_inspection"] }` on a test playbook.
2. Open an execution that has remote child steps and replay lineage.
3. Ask in the right panel: “這次 GPU 子任務失敗在哪裡？列出 child executions 與 target VM。”

**Pass**

- The backend enters agent mode.
- The model calls readonly execution tools only.
- The final assistant message references child execution / remote summary data that matches the center panel.

**Fail**

- The model cannot see remote child lineage because the tool catalog is incomplete.
- The agent falls back to guessing from plain prompt text.

### Scenario C: Agent mode proposes, but does not silently execute, a write action

**Steps**

1. Enable `x_platform.local_core.execution_chat.tool_groups=["execution_inspection", "execution_remote_control"]`.
2. Pick a failed remote child task.
3. Ask: “幫我重送這個失敗的 GPU step。”

**Pass**

- If runtime policy requires approval, the system persists a pending proposal and asks for confirmation instead of dispatching immediately.
- No resend occurs until the user confirms.

**Fail**

- The resend executes immediately even though `PolicyGuard` marked it as requiring approval.
- The agent loses the proposed arguments and cannot execute after confirmation.

### Scenario D: Confirming a pending resend proposal dispatches the correct child replay

**Steps**

1. Continue from Scenario C with a pending proposal.
2. Reply in execution chat with an explicit confirmation message.
3. Verify new child execution shell creation and lineage updates.

**Pass**

- A new child execution is created.
- `replay_of_execution_id`, `latest_replay_execution_id`, and `lineage_root_execution_id` are updated correctly.
- The final assistant message reports the new execution ID / target device.

**Fail**

- The confirmation message produces a new model guess instead of replaying the stored proposal.
- Replay lineage is missing or overwritten incorrectly.

## Phase 7: Evaluation & Automated Testing SOP

### Test Set T1: Route-mode dispatch

**Target**

- `backend/features/workspace/executions.py`

**Cases**

1. Resolved chat config `mode=discussion` -> route calls `generate_execution_chat_reply()` for non-paused messages.
2. Resolved chat config `mode=agent` -> route calls `handle_execution_chat_agent_turn()` and does not use `generate_text()` directly.
3. Legacy paused execution + `discussion` mode -> route still uses `continue_playbook_execution()`.

**Regression prevented**

- Prevents P1/P2 from reappearing through accidental route regression.

### Test Set T2: Builtin tool policy resolution fallback

**Target**

- `backend/app/services/tool_policy_resolver.py`

**Cases**

1. `workspace_get_execution_remote_summary` not present in `ToolRegistryService`, but present in `ToolListService` -> resolver synthesizes policy info with `risk_class="readonly"`.
2. `workspace_resend_remote_step` -> resolver synthesizes `risk_class="external_write"`.
3. Unknown tool absent from both registries -> resolver still returns `None`.

**Regression prevented**

- Prevents P3 from silently bypassing policy for builtin tools.

### Test Set T3: Approval semantics are enforced for execution-chat agent mode

**Target**

- `backend/app/services/playbook/tool_execution/policy.py`
- `backend/app/services/conversation/execution_chat_agent_service.py`

**Cases**

1. Action tool with `requires_approval=False` -> tool executes.
2. Action tool with `requires_approval=True` and `approval_mode="return_pending"` -> execution is skipped, pending proposal is returned.
3. Discussion/playbook mode with `approval_mode="log"` -> current behavior remains unchanged.

**Regression prevented**

- Prevents P4 from turning agent mode into an implicit write executor.

### Test Set T4: Execution-chat conversation manager compatibility with tool loop

**Target**

- `backend/app/services/conversation/execution_chat_conversation_manager.py`
- `backend/app/services/playbook/tool_execution/loop.py`

**Cases**

1. Valid tool-call JSON -> parsed and executed through the loop.
2. Wrong format (`function_call`, `tool_code`) -> format-repair path triggers and the next round retries.
3. No tool call -> loop exits cleanly with a final assistant message.

**Regression prevented**

- Prevents P7 and avoids reintroducing a second, divergent tool-call parser.

### Test Set T5: New execution tools return stable shapes

**Target**

- `backend/app/services/tools/workspace_tools.py`

**Cases**

1. `workspace_list_child_executions(parent_execution_id=...)` returns projected rows with `remote_execution_summary`.
2. `workspace_get_execution_remote_summary(execution_id=...)` reuses `build_remote_execution_summary()` shape.
3. `workspace_continue_execution(...)` delegates to `PlaybookRunner.continue_playbook_execution()`.
4. `workspace_resend_remote_step(...)` delegates to `resend_remote_workflow_step_child_task(...)`.

**Regression prevented**

- Prevents P5 by keeping execution-chat tools aligned with existing execution APIs/services.

### Test Set T6: End-to-end agent-mode execution chat

**Target**

- API + service integration test around `POST /api/v1/workspaces/{workspace_id}/executions/{execution_id}/chat`

**Cases**

1. Readonly inspection request returns a final `EXECUTION_CHAT` assistant event with `used_tools`.
2. Write-intent request creates a pending proposal event rather than immediate execution.
3. Confirmation request replays the pending proposal and creates a new child execution.

**Regression prevented**

- Protects the complete `right-panel -> agent -> tools -> execution lineage` architecture from collapsing back into prompt-only chat.
