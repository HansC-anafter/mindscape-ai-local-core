# Local-Core Wave A Execution / Orchestration Implementation Plan

Source inventory: `/Users/shock/Projects_local/workspace/mindscape-ai-local-core/.agent/plans/large-file-modularization/large-file-modularization-inventory-2026-03-23.md`

Parent plan:
- `/Users/shock/Projects_local/workspace/mindscape-ai-local-core/.agent/plans/large-file-modularization/local-core-implementation-modularization-plan-2026-03-23.md`

Scope:
- Wave A = execution / orchestration core
- Files covered: 8
- Goal: modularize the execution backbone without breaking active import paths, runtime callbacks, or meeting/dispatch flows

Files in scope:
- `/Users/shock/Projects_local/workspace/mindscape-ai-local-core/backend/app/services/workflow_orchestrator.py`
- `/Users/shock/Projects_local/workspace/mindscape-ai-local-core/backend/app/services/playbook_run_executor.py`
- `/Users/shock/Projects_local/workspace/mindscape-ai-local-core/backend/app/services/playbook_runner.py`
- `/Users/shock/Projects_local/workspace/mindscape-ai-local-core/backend/app/services/decision/coordinator.py`
- `/Users/shock/Projects_local/workspace/mindscape-ai-local-core/backend/app/services/orchestration/governance_engine.py`
- `/Users/shock/Projects_local/workspace/mindscape-ai-local-core/backend/app/services/orchestration/meeting/engine.py`
- `/Users/shock/Projects_local/workspace/mindscape-ai-local-core/backend/app/services/orchestration/meeting/_prompts.py`
- `/Users/shock/Projects_local/workspace/mindscape-ai-local-core/backend/app/services/orchestration/dispatch_orchestrator.py`

---

## Phase 1: Evidence Collection

### Evidence Items

- E1. `/Users/shock/Projects_local/workspace/mindscape-ai-local-core/backend/app/services/workflow_orchestrator.py:62`, `:454`, `:969`, `:1614`, and `:1997` show one class owning top-level workflow orchestration, playbook-step execution, single-step execution, and retry logic inside the same 2145-line file.
- E2. `/Users/shock/Projects_local/workspace/mindscape-ai-local-core/backend/app/services/playbook_run_executor.py:117`, `:163`, `:842`, `:939`, and `:1220` show one executor owning entrypoint dispatch, remote-execution routing, standalone handling, and legacy workflow fallback inside the same 1574-line file.
- E3. `/Users/shock/Projects_local/workspace/mindscape-ai-local-core/backend/app/services/playbook_runner.py:215`, `:277`, `:795`, and `:1207` show one service owning start, continue, and result retrieval for playbook execution while also holding run-state helpers above the class.
- E4. `/Users/shock/Projects_local/workspace/mindscape-ai-local-core/backend/app/services/decision/coordinator.py:236`, `:298`, `:432`, `:683`, and `:1133` show one coordinator owning decision synthesis, conflict logic, event/log persistence, and governance recording in a 1331-line file.
- E5. `/Users/shock/Projects_local/workspace/mindscape-ai-local-core/backend/app/services/orchestration/governance_engine.py:32`, `:100`, `:430`, `:600`, and `:977` show one engine handling completion ingress, webhook processing, legacy webhook bridging, provenance/artifact mutation, and follow-up task creation.
- E6. `/Users/shock/Projects_local/workspace/mindscape-ai-local-core/backend/app/services/orchestration/meeting/engine.py:86`, `:275`, `:435`, `:705`, and `:886` show `MeetingEngine` orchestrating stage flow, multi-round deliberation, dispatch handoff, and finalization in one file.
- E7. `/Users/shock/Projects_local/workspace/mindscape-ai-local-core/backend/app/services/orchestration/meeting/_prompts.py:41`, `:71`, `:654`, and `:1019` show one mixin owning workspace context assembly, tool inventory, turn prompt building, and full system message assembly across 1061 lines.
- E8. `/Users/shock/Projects_local/workspace/mindscape-ai-local-core/backend/app/services/orchestration/dispatch_orchestrator.py:34`, `:93`, `:318`, `:524`, and `:646` show one DAG walker owning graph traversal, phase dispatch, playbook launch, and tool dispatch in one file.
- E9. Caller verification by full-project grep shows these are all active compatibility surfaces: `WorkflowOrchestrator`/`workflow_orchestrator` = `14/5`, `PlaybookRunExecutor`/`playbook_run_executor` = `30/18`, `PlaybookRunner`/`playbook_runner` = `48/91`, `UnifiedDecisionCoordinator`/`decision.coordinator` = `11/19`, `GovernanceEngine`/`governance_engine` = `25/8`, `MeetingEngine`/`orchestration.meeting.engine` = `29/1`, `MeetingPromptsMixin`/`meeting._prompts` = `2/1`, `DispatchOrchestrator`/`dispatch_orchestrator` = `20/2`.
- E10. `/Users/shock/Projects_local/workspace/mindscape-ai-local-core/backend/tests/services/test_workflow_orchestrator.py`, `/Users/shock/Projects_local/workspace/mindscape-ai-local-core/backend/tests/test_workflow_orchestrator_remote_tool_routes.py`, `/Users/shock/Projects_local/workspace/mindscape-ai-local-core/backend/tests/test_playbook_runner_routing.py`, `/Users/shock/Projects_local/workspace/mindscape-ai-local-core/backend/tests/test_playbook_runner_event_metadata.py`, `/Users/shock/Projects_local/workspace/mindscape-ai-local-core/backend/tests/test_coordinator_facade_integration.py`, `/Users/shock/Projects_local/workspace/mindscape-ai-local-core/backend/tests/services/orchestration/test_governance_engine_unified.py`, `/Users/shock/Projects_local/workspace/mindscape-ai-local-core/backend/tests/services/orchestration/test_meeting_v6.py`, `/Users/shock/Projects_local/workspace/mindscape-ai-local-core/backend/tests/services/orchestration/test_meeting_prompt_injection.py`, and `/Users/shock/Projects_local/workspace/mindscape-ai-local-core/backend/tests/services/orchestration/test_dispatch_orchestrator.py` already exist, so the refactor has direct regression gates.
- E11. `git status --short` on local-core shows `/Users/shock/Projects_local/workspace/mindscape-ai-local-core/backend/app/services/workflow_orchestrator.py` is already modified in the working tree, so Wave A insertion points must be treated as verified against current working tree state, not historical HEAD.

### Phase 1.5: Historical Regression Analysis (Git History)

- H1. `/Users/shock/Projects_local/workspace/mindscape-ai-local-core/backend/app/services/workflow_orchestrator.py` absorbed execution chat, registry completion tracking, retry/error handling, and service stabilization in `42d1799`, `f7131ce`, `a2af848`, `b98ee2d`, and `1afb88d`.
- H2. `/Users/shock/Projects_local/workspace/mindscape-ai-local-core/backend/app/services/playbook_run_executor.py` accumulated meeting dispatch, remote callbacks, multimodal/runner stabilization, and supporting service expansion in `42d1799`, `442386e`, `643e19f`, `a2af848`, and `56253af`.
- H3. `/Users/shock/Projects_local/workspace/mindscape-ai-local-core/backend/app/services/playbook_runner.py` kept taking execution, variant, async DB, and PostgreSQL service changes in `42d1799`, `efef560`, `871027d`, `56d0caa`, and `ac971b7`.
- H4. `/Users/shock/Projects_local/workspace/mindscape-ai-local-core/backend/app/services/decision/coordinator.py` became the landing zone for decision, event-stream, and Pydantic/DB migrations in `e496827`, `56d0caa`, `4d32f50`, `64ad7dd`, and `6344c4b`.
- H5. `/Users/shock/Projects_local/workspace/mindscape-ai-local-core/backend/app/services/orchestration/governance_engine.py` expanded with execution chat and unified governance/remote callback handling in `42d1799` and `442386e`.
- H6. `/Users/shock/Projects_local/workspace/mindscape-ai-local-core/backend/app/services/orchestration/meeting/engine.py` absorbed meeting terminology changes, runtime/model/orchestrator components, and callback integration in `42d1799`, `442386e`, `643e19f`, `1afb88d`, and `3a92d10`.
- H7. `/Users/shock/Projects_local/workspace/mindscape-ai-local-core/backend/app/services/orchestration/meeting/_prompts.py` accumulated tool discovery, persona enrichment, meeting optimization, and execution-chat context in `42d1799`, `1afb88d`, `3a92d10`, `a370e6c`, and `aa9c6a3`.
- H8. `/Users/shock/Projects_local/workspace/mindscape-ai-local-core/backend/app/services/orchestration/dispatch_orchestrator.py` accumulated meeting-session, remote callback, and supporting-service changes in `42d1799`, `442386e`, `643e19f`, `1afb88d`, and `56253af`.

Conclusion from history:
- Every Wave A file grew by additive feature insertion.
- The fix is not another local cleanup pass; it is boundary extraction plus facade preservation.

---

## Phase 2: Problem Definition + Severity Scoring

1. **Execution entrypoint overload**: `workflow_orchestrator.py`, `playbook_run_executor.py`, and `playbook_runner.py` each combine orchestration, runtime dispatch, fallback logic, and result shaping, so execution changes land in multiple oversized files at once (E1, E2, E3, H1, H2, H3).
2. **Governance and decision coupling**: decision synthesis, completion ingress, follow-up generation, and persistence are split across two large files with overlapping responsibility over approval/governance outcomes (E4, E5, H4, H5).
3. **Meeting engine prompt entanglement**: stage orchestration and prompt compilation are separate files but still too large and tightly coupled, so meeting feature changes continue to touch both engine and prompt assembly at the same time (E6, E7, H6, H7).
4. **Dispatch boundary collapse**: `dispatch_orchestrator.py` owns graph traversal, playbook dispatch, tool dispatch, provenance, and activity publishing, so every dispatch rule change risks topology and emission regressions (E8, H8).
5. **Compatibility seam risk**: all 8 files have live callers, which means direct path moves without facades will cause breakage across backend services, scripts, and tests (E9, E10, E11).

### FMEA-lite Priority Table

| Problem | Severity | Detection | Priority |
|---|---:|---:|---:|
| P1 Execution entrypoint overload | 5 | 4 | 20 |
| P2 Governance and decision coupling | 4 | 4 | 16 |
| P3 Meeting engine prompt entanglement | 4 | 4 | 16 |
| P4 Dispatch boundary collapse | 4 | 4 | 16 |
| P5 Compatibility seam risk | 5 | 3 | 15 |

---

## Phase 3: Assumption Verification (CoVe)

| Assumption | Verification | Result |
|---|---|---|
| Wave A files can be moved without compatibility shims | Full-project grep for class names and module-path tokens | False; all 8 files have live callers, several with double-digit reference counts |
| `MeetingPromptsMixin` is broad public API | Full-project grep for `MeetingPromptsMixin` and `meeting._prompts` | Narrowly used, but still active; safe to convert into a thin mixin facade over extracted prompt builders |
| There are existing tests for each sub-area | Inspect `backend/tests/` and `backend/tests/services/orchestration/` | True; there are focused tests for workflow, runner, coordinator, governance, meeting, and dispatch |
| `workflow_orchestrator.py` line anchors are stable relative to current worktree | `git status --short` plus direct line audit | Partially false; file is modified locally, so final implementation must re-run citation audit before patching |
| Wave A can proceed without DB backup | Compare touched concerns against execution, tasks, artifacts, and follow-up creation flows | False; execution/governance changes can alter persisted state, so backup is mandatory |

---

## Phase 3.5: Pre-Mortem

1. **Import-cycle failure**
   - Likely failure mode: extracted `contracts.py` or `events.py` modules still import heavy services, causing cycles between orchestrator, runner, meeting, and governance packages.
   - Mitigation: create pure contract modules first and forbid them from importing service classes.
2. **Facade drift**
   - Likely failure mode: new subpackages work, but old module paths stop re-exporting one helper or class, breaking background call sites.
   - Mitigation: replace old file contents only after explicit `__all__` facades are written and caller grep is rerun.
3. **Behavioral split without test parity**
   - Likely failure mode: dispatch, retry, or prompt rendering is split into modules but loses edge-case ordering or metadata behavior.
   - Mitigation: run focused tests after each file migration and add missing contract tests before deleting old source blocks.

---

## Phase 4: Plan Writing

### Step A0: Backup and Shared Skeleton

Resolves Problem #1, Problem #2, Problem #3, Problem #4, Problem #5

Before any Wave A implementation work:

```bash
docker compose exec -T postgres pg_dump -U mindscape -d mindscape_core > data/backups/mindscape_core_pre_test_$(date +%Y%m%d_%H%M%S).sql
```

Then create shared Wave A foundations first:
- `backend/app/services/execution_core/clock.py`
- `backend/app/services/execution_core/contracts.py`
- `backend/app/services/execution_core/errors.py`
- `backend/app/services/execution_core/events.py`

Rules:
- These files must stay pure and import-light.
- Every old Wave A file remains import-compatible until its caller grep reaches zero or is intentionally preserved as a facade.

### A1. `/Users/shock/Projects_local/workspace/mindscape-ai-local-core/backend/app/services/workflow_orchestrator.py`

Resolves Problem #1 and Problem #5

Verified anchors:
- `/Users/shock/Projects_local/workspace/mindscape-ai-local-core/backend/app/services/workflow_orchestrator.py:62`
- `/Users/shock/Projects_local/workspace/mindscape-ai-local-core/backend/app/services/workflow_orchestrator.py:454`
- `/Users/shock/Projects_local/workspace/mindscape-ai-local-core/backend/app/services/workflow_orchestrator.py:969`
- `/Users/shock/Projects_local/workspace/mindscape-ai-local-core/backend/app/services/workflow_orchestrator.py:1614`
- `/Users/shock/Projects_local/workspace/mindscape-ai-local-core/backend/app/services/workflow_orchestrator.py:1997`

Implementation details:
- Create `backend/app/services/workflow/` with:
  - `orchestrator.py`: `WorkflowOrchestrator.execute_workflow()`
  - `step_dispatch.py`: `_execute_playbook_steps()`, `_execute_single_step_iteration()`, `_execute_single_step()`
  - `dependency_graph.py`: `_build_dependency_graph()`, `_get_ready_steps()`, `_get_ready_steps_for_parallel()`, `_evaluate_condition()`
  - `retry_policy.py`: `_execute_step_with_retry()`, `_get_default_retry_policy()`, `_calculate_retry_delay()`, `_classify_error()`
  - `result_mapper.py`: `_collect_final_outputs()`, `_create_step_event()`
  - `remote_route.py`: `_get_cloud_connector()`, `_resolve_remote_tool_route()`, `_resolve_tool_model_override()`, `_maybe_execute_tool_via_remote_route()`
- Move `_utc_now()` into `execution_core/clock.py`.
- Move `RecoverableStepError` into `execution_core/errors.py`.
- Leave `workflow_orchestrator.py` as a compatibility facade exporting `WorkflowOrchestrator` and `RecoverableStepError`.

Precise replacement logic:
- First extraction commit keeps method bodies byte-for-byte moved into new modules.
- Second commit rewrites `workflow_orchestrator.py` to imports only.
- Do not inline-call new helpers from old file permanently; the old file must become a facade, not another coordination layer.

Verification commands:

```bash
pytest backend/tests/services/test_workflow_orchestrator.py \
  backend/tests/test_workflow_orchestrator_remote_tool_routes.py \
  backend/tests/test_execution_plan_flow.py
```

### A2. `/Users/shock/Projects_local/workspace/mindscape-ai-local-core/backend/app/services/playbook_run_executor.py`

Resolves Problem #1 and Problem #5

Verified anchors:
- `/Users/shock/Projects_local/workspace/mindscape-ai-local-core/backend/app/services/playbook_run_executor.py:117`
- `/Users/shock/Projects_local/workspace/mindscape-ai-local-core/backend/app/services/playbook_run_executor.py:163`
- `/Users/shock/Projects_local/workspace/mindscape-ai-local-core/backend/app/services/playbook_run_executor.py:842`
- `/Users/shock/Projects_local/workspace/mindscape-ai-local-core/backend/app/services/playbook_run_executor.py:939`
- `/Users/shock/Projects_local/workspace/mindscape-ai-local-core/backend/app/services/playbook_run_executor.py:1220`

Implementation details:
- Create `backend/app/services/playbook_run/` with:
  - `executor.py`: public `PlaybookRunExecutor`
  - `dispatch.py`: `_maybe_dispatch_remote_execution()`, `_get_execution_dispatch_helpers()`
  - `standalone.py`: `_handle_standalone()`, `_execute_workflow_standalone()`, `_execute_conversation_standalone()`
  - `plan_node.py`: `_handle_plan_node()`, `_execute_workflow_plan_node()`, `_execute_conversation_plan_node()`
  - `legacy_workflow.py`: `_execute_workflow_legacy()`
  - `runtime_loader.py`: `_load_runtime_providers()`
  - `error_policy.py`: `_workflow_result_has_errors()`, `_runtime_result_has_errors()`
- Move `_utc_now()` into shared clock and keep executor-local helpers only where they are not reused.
- Preserve `execute_playbook_run()` as the single public method on the exported facade.

Precise replacement logic:
- New package owns the implementation; old module re-exports `PlaybookRunExecutor`.
- Remote-dispatch and legacy-workflow helpers must not remain co-located after extraction, because they are the two highest-risk growth vectors in this file.

Verification commands:

```bash
pytest backend/tests/test_playbook_executor_meeting_context.py \
  backend/tests/test_execution_runner_metadata.py \
  backend/tests/test_execution_chat_agent_service.py
```

### A3. `/Users/shock/Projects_local/workspace/mindscape-ai-local-core/backend/app/services/playbook_runner.py`

Resolves Problem #1 and Problem #5

Verified anchors:
- `/Users/shock/Projects_local/workspace/mindscape-ai-local-core/backend/app/services/playbook_runner.py:215`
- `/Users/shock/Projects_local/workspace/mindscape-ai-local-core/backend/app/services/playbook_runner.py:277`
- `/Users/shock/Projects_local/workspace/mindscape-ai-local-core/backend/app/services/playbook_runner.py:795`
- `/Users/shock/Projects_local/workspace/mindscape-ai-local-core/backend/app/services/playbook_runner.py:1207`

Implementation details:
- Create `backend/app/services/playbook_runner_core/` with:
  - `runner.py`: public `PlaybookRunner`
  - `run_state.py`: `_build_run_state_context()`, `_build_run_state_payload()`, `_build_run_state_metadata()`, `_build_run_state_changed_event()`
  - `start_flow.py`: `start_playbook_execution()`
  - `continue_flow.py`: `continue_playbook_execution()`
  - `results.py`: `get_playbook_execution_result()`, `cleanup_execution()`, `list_active_executions()`
  - `normalization.py`: `_normalize_optional_text()`, `_normalize_optional_handle()`, `_derive_pack_id()`, `_derive_refresh_hint()`, `_derive_ui_surface()`
- Keep `playbook_runner.py` as a facade because caller counts are the highest in Wave A.
- Do not duplicate state-payload builder logic inside both runner and execution chat modules after extraction.

Precise replacement logic:
- Preserve the `PlaybookRunner` class name and import path.
- Split helper groups before touching public methods so start/continue/result code can import a stable run-state module.

Verification commands:

```bash
pytest backend/tests/test_playbook_runner_routing.py \
  backend/tests/test_playbook_runner_event_metadata.py \
  backend/tests/test_runner_task_executor_events.py
```

### A4. `/Users/shock/Projects_local/workspace/mindscape-ai-local-core/backend/app/services/decision/coordinator.py`

Resolves Problem #2 and Problem #5

Verified anchors:
- `/Users/shock/Projects_local/workspace/mindscape-ai-local-core/backend/app/services/decision/coordinator.py:236`
- `/Users/shock/Projects_local/workspace/mindscape-ai-local-core/backend/app/services/decision/coordinator.py:298`
- `/Users/shock/Projects_local/workspace/mindscape-ai-local-core/backend/app/services/decision/coordinator.py:432`
- `/Users/shock/Projects_local/workspace/mindscape-ai-local-core/backend/app/services/decision/coordinator.py:683`
- `/Users/shock/Projects_local/workspace/mindscape-ai-local-core/backend/app/services/decision/coordinator.py:1133`

Implementation details:
- Create `backend/app/services/decision/core/` with:
  - `contracts.py`: `PlaybookCandidate`, `IntentRoutingDecision`, `PlaybookPreflightResult`, `NodeGovernanceDecision`, `CostGovernanceDecision`, `PolicyDecision`, `MemoryRecommendation`, `UnifiedDecisionResult`
  - `coordinator.py`: public `UnifiedDecisionCoordinator`
  - `synthesis.py`: `_synthesize_decision()`, `_all_layers_agree()`, `_detect_conflicts()`, `_resolve_conflicts()`
  - `policies.py`: `_can_auto_execute()`, `_requires_user_approval()`
  - `persistence.py`: `_store_decision_to_intent_log()`, `_record_governance_decisions()`
  - `serialization.py`: `_serialize_*` helpers
  - `events.py`: `_emit_decision_required_event()`, `_emit_branch_proposed_event()`, `_build_governance_decision_payload()`
- Keep one thin module at the old path exporting `UnifiedDecisionCoordinator` and contract types.

Precise replacement logic:
- Move DTOs first, then synthesis/persistence/event logic, then the coordinator shell.
- Do not leave DTO classes inside the coordinator module after extraction; that preserves the current monolith.

Verification commands:

```bash
pytest backend/tests/test_coordinator_facade_integration.py \
  backend/tests/test_chat_endpoint_execution_plan.py \
  backend/tests/test_execution_metadata_governance.py
```

### A5. `/Users/shock/Projects_local/workspace/mindscape-ai-local-core/backend/app/services/orchestration/governance_engine.py`

Resolves Problem #2 and Problem #5

Verified anchors:
- `/Users/shock/Projects_local/workspace/mindscape-ai-local-core/backend/app/services/orchestration/governance_engine.py:32`
- `/Users/shock/Projects_local/workspace/mindscape-ai-local-core/backend/app/services/orchestration/governance_engine.py:100`
- `/Users/shock/Projects_local/workspace/mindscape-ai-local-core/backend/app/services/orchestration/governance_engine.py:430`
- `/Users/shock/Projects_local/workspace/mindscape-ai-local-core/backend/app/services/orchestration/governance_engine.py:600`
- `/Users/shock/Projects_local/workspace/mindscape-ai-local-core/backend/app/services/orchestration/governance_engine.py:977`

Implementation details:
- Create `backend/app/services/orchestration/governance/` with:
  - `engine.py`: public `GovernanceEngine`
  - `completion_ingress.py`: `process_completion()`, `process_remote_terminal_event()`
  - `webhook_bridge.py`: `process_playbook_webhook()`, `_invoke_legacy_webhook_handler()`
  - `artifact_metadata.py`: `_register_project_artifact()`, `_update_artifact_metadata()`
  - `provenance.py`: `_backfill_provenance()`, `_merge_provenance()`, `_resolve_governance_payload()`, `_sync_correctness_signals()`, `_backfill_eval_summary()`, `_merge_eval_summary()`
  - `follow_up.py`: `_resolve_acceptance_tests()`, `_calculate_acceptance_pass_rate()`, `_trigger_follow_up()`, `_create_follow_up_task()`
- Keep adapter/store property accessors in `engine.py` only if they are needed by multiple submodules; otherwise push them into a dependency container.

Precise replacement logic:
- First extract provenance and follow-up helpers because they are the least public but the most side-effect-heavy.
- Then split ingress/webhook paths.
- Final file should export a thin `GovernanceEngine` with delegated methods, not carry the whole implementation.

Verification commands:

```bash
pytest backend/tests/services/orchestration/test_governance_engine_unified.py \
  backend/tests/services/orchestration/test_governance_engine_governance_payload.py \
  backend/tests/services/orchestration/test_governance_provenance_backfill.py
```

### A6. `/Users/shock/Projects_local/workspace/mindscape-ai-local-core/backend/app/services/orchestration/meeting/engine.py`

Resolves Problem #3 and Problem #5

Verified anchors:
- `/Users/shock/Projects_local/workspace/mindscape-ai-local-core/backend/app/services/orchestration/meeting/engine.py:86`
- `/Users/shock/Projects_local/workspace/mindscape-ai-local-core/backend/app/services/orchestration/meeting/engine.py:275`
- `/Users/shock/Projects_local/workspace/mindscape-ai-local-core/backend/app/services/orchestration/meeting/engine.py:435`
- `/Users/shock/Projects_local/workspace/mindscape-ai-local-core/backend/app/services/orchestration/meeting/engine.py:705`
- `/Users/shock/Projects_local/workspace/mindscape-ai-local-core/backend/app/services/orchestration/meeting/engine.py:886`

Implementation details:
- Create `backend/app/services/orchestration/meeting/runtime/` with:
  - `engine.py`: public `MeetingEngine.run()`
  - `contracts.py`: `RoleTurnResult`, `MeetingResult`
  - `agenda_stage.py`: `_stage_agenda_and_rag()`
  - `contract_stage.py`: `_stage_compile_contract()`
  - `deliberation_stage.py`: `_stage_deliberation()`, `_role_turn()`, supervisor helpers
  - `dispatch_stage.py`: `_stage_decompose_and_dispatch()`
  - `finalize.py`: `_stage_finalize()`
  - `infra.py`: `_get_handoff_registry_store()`, `_get_pack_dispatch_adapter()`, `_emit_meeting_stage()`
- Keep the mixin composition at the public class level if needed, but move stage bodies into dedicated modules.

Precise replacement logic:
- The old `engine.py` becomes a coordinator shell that wires stage modules in order.
- Do not keep stage bodies as private methods in the shell after extraction; that would keep the file large while pretending to modularize.

Verification commands:

```bash
pytest backend/tests/services/orchestration/test_meeting_v6.py \
  backend/tests/services/orchestration/test_meeting_supervisor.py \
  backend/tests/services/orchestration/test_meeting_dispatch.py
```

### A7. `/Users/shock/Projects_local/workspace/mindscape-ai-local-core/backend/app/services/orchestration/meeting/_prompts.py`

Resolves Problem #3 and Problem #5

Verified anchors:
- `/Users/shock/Projects_local/workspace/mindscape-ai-local-core/backend/app/services/orchestration/meeting/_prompts.py:41`
- `/Users/shock/Projects_local/workspace/mindscape-ai-local-core/backend/app/services/orchestration/meeting/_prompts.py:71`
- `/Users/shock/Projects_local/workspace/mindscape-ai-local-core/backend/app/services/orchestration/meeting/_prompts.py:654`
- `/Users/shock/Projects_local/workspace/mindscape-ai-local-core/backend/app/services/orchestration/meeting/_prompts.py:1019`

Implementation details:
- Create `backend/app/services/orchestration/meeting/prompts/` with:
  - `workspace_context.py`: `_build_workspace_instruction_block()`, workspace identity helpers
  - `tool_inventory.py`: `_build_tool_inventory_block()`, `_has_workspace_tool_bindings()`, `_verb_augment()`, `_build_tool_query_from_context()`
  - `project_context.py`: `_build_project_context()`, `_build_asset_map_context()`, `_build_lens_context()`, `_build_previous_decisions_context()`
  - `turn_prompt.py`: `_build_turn_prompt()`, `_fallback_turn_text()`, `_is_converged()`, `_extract_meeting_topic()`
  - `minutes.py`: `_render_minutes()`, `_history_snippet()`
  - `system_message.py`: `_assemble_system_message()`
- Keep `_prompts.py` as a thin `MeetingPromptsMixin` compatibility layer delegating to the extracted prompt builders.

Precise replacement logic:
- Preserve method names on the mixin so `MeetingEngine` can continue calling them unchanged during the transition.
- Extract context builders first, because they are the most stable seams and the least likely to create behavior drift.

Verification commands:

```bash
pytest backend/tests/services/orchestration/test_meeting_prompt_injection.py \
  backend/tests/test_agent_mode_prompt_verification.py \
  backend/tests/services/orchestration/test_meeting_asset_map.py
```

### A8. `/Users/shock/Projects_local/workspace/mindscape-ai-local-core/backend/app/services/orchestration/dispatch_orchestrator.py`

Resolves Problem #4 and Problem #5

Verified anchors:
- `/Users/shock/Projects_local/workspace/mindscape-ai-local-core/backend/app/services/orchestration/dispatch_orchestrator.py:34`
- `/Users/shock/Projects_local/workspace/mindscape-ai-local-core/backend/app/services/orchestration/dispatch_orchestrator.py:93`
- `/Users/shock/Projects_local/workspace/mindscape-ai-local-core/backend/app/services/orchestration/dispatch_orchestrator.py:318`
- `/Users/shock/Projects_local/workspace/mindscape-ai-local-core/backend/app/services/orchestration/dispatch_orchestrator.py:524`
- `/Users/shock/Projects_local/workspace/mindscape-ai-local-core/backend/app/services/orchestration/dispatch_orchestrator.py:646`

Implementation details:
- Create `backend/app/services/orchestration/dispatch/` with:
  - `orchestrator.py`: public `DispatchOrchestrator.execute()`
  - `phase_dispatch.py`: `_dispatch_phase()`
  - `playbook_launch.py`: `_launch_playbook()`
  - `tool_dispatch.py`: `_dispatch_tool()`
  - `attempts.py`: `_create_attempt()`, `get_attempt()`, `get_all_attempts()`
  - `topology.py`: `_should_skip()`, DAG walk helpers
  - `provenance.py`: `_normalize_phase_inputs()`, `_derive_research_context()`, `_build_ir_provenance()`
  - `activity.py`: `_publish_activity()`
- Preserve the class path as a facade because it still has active callers.

Precise replacement logic:
- Extract `attempts.py` and `topology.py` before dispatch helpers so phase-walk state stops living in the same file as launch side effects.
- Keep the public `execute()` method in the facade shell until all direct imports are migrated.

Verification commands:

```bash
pytest backend/tests/services/orchestration/test_dispatch_orchestrator.py \
  backend/tests/services/orchestration/test_dispatch_orchestrator_idempotency.py \
  backend/tests/services/orchestration/test_dispatch_policy_gate.py
```

---

## Phase 5: Citation Audit (CoVe Final Pass)

Critical insertion points re-verified during plan writing:
- `/Users/shock/Projects_local/workspace/mindscape-ai-local-core/backend/app/services/workflow_orchestrator.py:62`
- `/Users/shock/Projects_local/workspace/mindscape-ai-local-core/backend/app/services/playbook_run_executor.py:117`
- `/Users/shock/Projects_local/workspace/mindscape-ai-local-core/backend/app/services/playbook_runner.py:215`
- `/Users/shock/Projects_local/workspace/mindscape-ai-local-core/backend/app/services/decision/coordinator.py:236`
- `/Users/shock/Projects_local/workspace/mindscape-ai-local-core/backend/app/services/orchestration/governance_engine.py:32`
- `/Users/shock/Projects_local/workspace/mindscape-ai-local-core/backend/app/services/orchestration/meeting/engine.py:86`
- `/Users/shock/Projects_local/workspace/mindscape-ai-local-core/backend/app/services/orchestration/meeting/_prompts.py:41`
- `/Users/shock/Projects_local/workspace/mindscape-ai-local-core/backend/app/services/orchestration/dispatch_orchestrator.py:34`

Caller-path assumptions re-verified:
- All 8 old module paths are active and require facades
- `_prompts.py` can become a delegating mixin rather than a removed file
- `workflow_orchestrator.py` line numbers reflect current modified worktree state

---

## Phase 6: Validation SOP

### SOP

1. Take the PostgreSQL backup.
2. Add `execution_core/` and the destination packages for Wave A.
3. Extract pure contracts/helpers first.
4. Extract one file at a time in the order A7 -> A6 -> A8 -> A5 -> A4 -> A1 -> A2 -> A3.
5. After each file extraction:
   - run the file-specific tests
   - rerun a caller grep on the original path
   - confirm the original file is now a facade only
6. After all 8 are migrated, run the full Wave A regression suite.

### Manual verification scenarios

1. **Remote workflow execution**
   - Start a workflow that can route through remote execution.
   - Pass: dispatch, retry, and final outputs behave identically to pre-refactor behavior.
   - Fail: remote route lookup, retry policy, or final event payload changes unexpectedly.
2. **Meeting-to-dispatch flow**
   - Trigger a meeting flow that deliberates and dispatches action items.
   - Pass: meeting stages emit, prompts render, dispatch attempts are recorded, and governance follow-ups still appear.
   - Fail: prompt assembly misses context, dispatch skips phases, or governance payload is incomplete.
3. **Playbook execution lifecycle**
   - Start, continue, and inspect a playbook execution.
   - Pass: execution state, run-state metadata, and result retrieval remain stable.
   - Fail: conversation continuation breaks or result retrieval no longer finds final structured output.

### Full Wave A regression suite

```bash
pytest backend/tests/services/test_workflow_orchestrator.py \
  backend/tests/test_workflow_orchestrator_remote_tool_routes.py \
  backend/tests/test_execution_plan_flow.py \
  backend/tests/test_playbook_executor_meeting_context.py \
  backend/tests/test_execution_runner_metadata.py \
  backend/tests/test_playbook_runner_routing.py \
  backend/tests/test_playbook_runner_event_metadata.py \
  backend/tests/test_coordinator_facade_integration.py \
  backend/tests/services/orchestration/test_governance_engine_unified.py \
  backend/tests/services/orchestration/test_meeting_v6.py \
  backend/tests/services/orchestration/test_meeting_prompt_injection.py \
  backend/tests/services/orchestration/test_dispatch_orchestrator.py
```

Pass criteria:
- All legacy import paths still resolve.
- Execution, meeting, governance, and dispatch tests remain green.
- Original 8 files are reduced to facade thickness or narrow shells.

Fail criteria:
- Any file still contains both high-level orchestration and extracted helper bodies.
- Any caller grep reveals broken imports or duplicate implementations.

---

## Phase 7: Evaluation & Automated Testing SOP

### Additional tests to add during Wave A

1. **Facade import contract test**
   - Input: import each old Wave A module path and instantiate the public class.
   - Expected output: old paths still export the same public symbols.
   - Prevents: Problem #5.
2. **Execution-core contract test**
   - Input: synthetic workflow with dependency graph, retry, and remote-route conditions.
   - Mock setup: fake tool executor, fake connector, fixed clock.
   - Expected output: orchestrator and playbook-run extraction preserve ordering and retry semantics.
   - Prevents: Problem #1.
3. **Meeting prompt/render contract test**
   - Input: workspace context with tool bindings, project context, and decision history.
   - Mock setup: fake meeting engine context.
   - Expected output: extracted prompt builders produce the same assembled system message and turn prompt.
   - Prevents: Problem #3.
4. **Dispatch attempt persistence test**
   - Input: multi-phase TaskIR with one skipped phase, one playbook phase, one tool phase.
   - Expected output: attempt records and activity publishing remain deterministic after extraction.
   - Prevents: Problem #4.

If any of these tests are too expensive to add inside the same refactor slice, add the import-contract test first and treat the rest as blocking follow-ups before removing the final legacy helper bodies.

---

## Appendix A: Wave A Dependency Order

1. Extract `meeting/_prompts.py` first so `MeetingEngine` can depend on smaller prompt builders.
2. Extract `meeting/engine.py` second so stage orchestration shrinks before governance and dispatch depend on it.
3. Extract `dispatch_orchestrator.py` third so meeting handoff targets a thinner dispatch surface.
4. Extract `governance_engine.py` and `decision/coordinator.py` next so post-dispatch persistence and follow-up logic stop expanding.
5. Extract `workflow_orchestrator.py`, `playbook_run_executor.py`, and `playbook_runner.py` last, because they have the broadest caller footprint and benefit from the shared modules created by earlier steps.

## Appendix B: Expected End State

- All 8 legacy files remain as compatibility facades or thin shells.
- Execution, meeting, governance, and dispatch logic live in package directories rather than mega-files.
- New shared contracts and errors sit in import-light modules.
- Future feature work lands in narrow submodules instead of re-inflating the original 8 files.

## Appendix B1: Per-File Plan Index

- Index: `/Users/shock/Projects_local/workspace/mindscape-ai-local-core/.agent/plans/large-file-modularization/wave-a-file-plans/README.md`
- `/Users/shock/Projects_local/workspace/mindscape-ai-local-core/backend/app/services/workflow_orchestrator.py` -> `/Users/shock/Projects_local/workspace/mindscape-ai-local-core/.agent/plans/large-file-modularization/wave-a-file-plans/workflow-orchestrator.md`
- `/Users/shock/Projects_local/workspace/mindscape-ai-local-core/backend/app/services/playbook_run_executor.py` -> `/Users/shock/Projects_local/workspace/mindscape-ai-local-core/.agent/plans/large-file-modularization/wave-a-file-plans/playbook-run-executor.md`
- `/Users/shock/Projects_local/workspace/mindscape-ai-local-core/backend/app/services/playbook_runner.py` -> `/Users/shock/Projects_local/workspace/mindscape-ai-local-core/.agent/plans/large-file-modularization/wave-a-file-plans/playbook-runner.md`
- `/Users/shock/Projects_local/workspace/mindscape-ai-local-core/backend/app/services/decision/coordinator.py` -> `/Users/shock/Projects_local/workspace/mindscape-ai-local-core/.agent/plans/large-file-modularization/wave-a-file-plans/decision-coordinator.md`
- `/Users/shock/Projects_local/workspace/mindscape-ai-local-core/backend/app/services/orchestration/governance_engine.py` -> `/Users/shock/Projects_local/workspace/mindscape-ai-local-core/.agent/plans/large-file-modularization/wave-a-file-plans/governance-engine.md`
- `/Users/shock/Projects_local/workspace/mindscape-ai-local-core/backend/app/services/orchestration/meeting/engine.py` -> `/Users/shock/Projects_local/workspace/mindscape-ai-local-core/.agent/plans/large-file-modularization/wave-a-file-plans/meeting-engine.md`
- `/Users/shock/Projects_local/workspace/mindscape-ai-local-core/backend/app/services/orchestration/meeting/_prompts.py` -> `/Users/shock/Projects_local/workspace/mindscape-ai-local-core/.agent/plans/large-file-modularization/wave-a-file-plans/meeting-prompts.md`
- `/Users/shock/Projects_local/workspace/mindscape-ai-local-core/backend/app/services/orchestration/dispatch_orchestrator.py` -> `/Users/shock/Projects_local/workspace/mindscape-ai-local-core/.agent/plans/large-file-modularization/wave-a-file-plans/dispatch-orchestrator.md`

## Appendix C: Do-Not-Miss Migration Checklist

Use this checklist during implementation. A file is not considered "done" until every line for that file is satisfied.

### C1. `/Users/shock/Projects_local/workspace/mindscape-ai-local-core/backend/app/services/workflow_orchestrator.py`

- [ ] `WorkflowOrchestrator` public import path still works
- [ ] remote-route helpers moved to `workflow/remote_route.py`
- [ ] dependency-graph helpers moved to `workflow/dependency_graph.py`
- [ ] step execution helpers moved to `workflow/step_dispatch.py`
- [ ] retry/error helpers moved to `workflow/retry_policy.py`
- [ ] result/event helpers moved to `workflow/result_mapper.py`
- [ ] `_utc_now()` removed to shared clock
- [ ] `RecoverableStepError` removed to shared errors
- [ ] old file reduced to facade/shell only
- [ ] `backend/tests/services/test_workflow_orchestrator.py` passes
- [ ] `backend/tests/test_workflow_orchestrator_remote_tool_routes.py` passes

### C2. `/Users/shock/Projects_local/workspace/mindscape-ai-local-core/backend/app/services/playbook_run_executor.py`

- [ ] `PlaybookRunExecutor` public import path still works
- [ ] remote dispatch extracted
- [ ] standalone execution extracted
- [ ] plan-node execution extracted
- [ ] legacy workflow path extracted
- [ ] runtime-provider loading extracted
- [ ] error classification helpers extracted
- [ ] old file reduced to facade/shell only
- [ ] `backend/tests/test_playbook_executor_meeting_context.py` passes
- [ ] `backend/tests/test_execution_runner_metadata.py` passes

### C3. `/Users/shock/Projects_local/workspace/mindscape-ai-local-core/backend/app/services/playbook_runner.py`

- [ ] `PlaybookRunner` public import path still works
- [ ] run-state payload/context/event builders extracted
- [ ] start flow extracted
- [ ] continue flow extracted
- [ ] results/cleanup/list extracted
- [ ] normalization helpers extracted
- [ ] old file reduced to facade/shell only
- [ ] `backend/tests/test_playbook_runner_routing.py` passes
- [ ] `backend/tests/test_playbook_runner_event_metadata.py` passes

### C4. `/Users/shock/Projects_local/workspace/mindscape-ai-local-core/backend/app/services/decision/coordinator.py`

- [ ] `UnifiedDecisionCoordinator` public import path still works
- [ ] DTO/contracts moved out of coordinator module
- [ ] synthesis/conflict logic extracted
- [ ] policy checks extracted
- [ ] persistence logic extracted
- [ ] event emission extracted
- [ ] serialization helpers extracted
- [ ] old file reduced to facade/shell only
- [ ] `backend/tests/test_coordinator_facade_integration.py` passes
- [ ] `backend/tests/test_chat_endpoint_execution_plan.py` passes

### C5. `/Users/shock/Projects_local/workspace/mindscape-ai-local-core/backend/app/services/orchestration/governance_engine.py`

- [ ] `GovernanceEngine` public import path still works
- [ ] completion ingress extracted
- [ ] webhook bridge extracted
- [ ] artifact metadata mutation extracted
- [ ] provenance/eval backfill extracted
- [ ] follow-up task creation extracted
- [ ] old file reduced to facade/shell only
- [ ] `backend/tests/services/orchestration/test_governance_engine_unified.py` passes
- [ ] `backend/tests/services/orchestration/test_governance_engine_governance_payload.py` passes

### C6. `/Users/shock/Projects_local/workspace/mindscape-ai-local-core/backend/app/services/orchestration/meeting/engine.py`

- [ ] `MeetingEngine` public import path still works
- [ ] contracts moved out of engine
- [ ] agenda stage extracted
- [ ] contract compile stage extracted
- [ ] deliberation stage extracted
- [ ] dispatch stage extracted
- [ ] finalize stage extracted
- [ ] infra/store adapter helpers extracted
- [ ] old file reduced to coordinator shell only
- [ ] `backend/tests/services/orchestration/test_meeting_v6.py` passes
- [ ] `backend/tests/services/orchestration/test_meeting_supervisor.py` passes

### C7. `/Users/shock/Projects_local/workspace/mindscape-ai-local-core/backend/app/services/orchestration/meeting/_prompts.py`

- [ ] `MeetingPromptsMixin` import path still works
- [ ] workspace context builders extracted
- [ ] tool inventory builders extracted
- [ ] project/lens/decision context builders extracted
- [ ] turn prompt builders extracted
- [ ] minutes/history rendering extracted
- [ ] system message assembly extracted
- [ ] old file reduced to delegating mixin only
- [ ] `backend/tests/services/orchestration/test_meeting_prompt_injection.py` passes
- [ ] `backend/tests/services/orchestration/test_meeting_asset_map.py` passes

### C8. `/Users/shock/Projects_local/workspace/mindscape-ai-local-core/backend/app/services/orchestration/dispatch_orchestrator.py`

- [ ] `DispatchOrchestrator` public import path still works
- [ ] topology walk extracted
- [ ] phase dispatch extracted
- [ ] playbook launch extracted
- [ ] tool dispatch extracted
- [ ] attempts state extracted
- [ ] provenance/input normalization extracted
- [ ] activity publishing extracted
- [ ] old file reduced to facade/shell only
- [ ] `backend/tests/services/orchestration/test_dispatch_orchestrator.py` passes
- [ ] `backend/tests/services/orchestration/test_dispatch_orchestrator_idempotency.py` passes

### Cross-file exit criteria

- [ ] all 8 old module paths still import successfully
- [ ] no new import cycle introduced
- [ ] shared `execution_core` modules remain import-light
- [ ] caller grep rerun after each extraction
- [ ] Wave A full regression suite passes before declaring the wave complete
