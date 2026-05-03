# Meeting Command Envelope And Collaboration Ledger Implementation Plan

Implementation progress on 2026-05-02: the backend contract seed is now implemented in local-core. The completed slice includes `MeetingCommandEnvelope`, `MeetingCommandStore`, server-side P0 grammar normalization, workspace-scoped `GET/POST /meetings/{meeting_id}/commands`, command-ledger projection into the meeting execution graph, route-owned object-action/playbook/chat dispatch, command status sync from runtime completion, command lifecycle status mapping for graph UI visibility, Meeting Workbench refresh from shared workspace SSE events, and removal of frontend command-submit compatibility fallback. Frontend command submit now writes a command row first. For role-bearing object-action commands, the command route can plan/invoke the object action, update the command row, and return `dispatch_result`; the frontend then stops local compatibility plan/invoke. For selected pack tools, the command route now calls the existing orchestrator `execute_playbook` path and returns playbook dispatch evidence; the frontend then stops local `/chat` compatibility dispatch. For ordinary chat commands, the command route schedules `ChatOrchestratorService.run_background_chat` and returns chat dispatch evidence; the frontend then stops local `/chat` compatibility dispatch. Task-backed runtime work now syncs command rows from accepted/running into completed/failed through `TasksStore`, and chat-only background dispatch marks command rows completed/failed when the chat service returns. Execution graph command nodes preserve raw durable lifecycle as `metadata.ledger_status` while exposing the UI graph status vocabulary, so accepted/completed/failed ledger rows do not disappear in the canvas. If a command response has no route-owned `dispatch_result`, the frontend treats it as a backend contract error instead of falling back to direct runtime calls.

## 1. Problem list

1. **The command bar is acting as the collaboration entrypoint, but there is no first-class command envelope API**: `AOLMeetingBottomShell` currently builds `meeting_id`, `meeting_session_id`, `thread_id`, `meeting_command`, selected object fields, mentions, and object action plans inside the React submit handler. Evidence: E1. Severity: 5. Detection: 4. Priority: 20.
2. **The meeting center is not expressed as a durable command ledger**: `MeetingSession` has status, agenda, decisions, traces, action items, minutes, and metadata, but inserted commands are still primarily inferred through events/tasks and `sendMessage` action params. Evidence: E2, E3, E4. Severity: 5. Detection: 4. Priority: 20.
3. **"Action buttons everywhere" would duplicate UI paths instead of unifying collaboration**: the platform already defines object-driven actions and generic verbs, but the primary UX should use command grammar plus `@object` references, with UI surfaces only inserting references or command templates. Evidence: E5, E6, E7. Severity: 4. Detection: 3. Priority: 12.
4. **Commands can originate from many surfaces, but local-core lacks a normalized origin model**: IG cards, PD scene rows, artifacts, inspector actions, and the command bar should all submit the same envelope, including origin surface, role-bearing objects, requested verb, write mode, and expected outputs. Evidence: E1, E5, E8. Severity: 4. Detection: 4. Priority: 16.
5. **The canvas cannot reliably show the meeting as the central collaboration platform until commands, runtime outputs, and provenance share one ledger identity**: execution graph currently composes nodes and edges from tasks, relations, events, and artifacts, but command identity is not a stable frontend/backend contract. Evidence: E4, E9. Severity: 5. Detection: 3. Priority: 15.
6. **The new command API must align with the existing workspace router and meeting-session lifecycle**: workspace-scoped runtime routes are mounted below `/api/v1/workspaces`, execution graph already uses `/meetings/{meeting_id}`, while lifecycle management still lives under `/meeting-sessions`; the plan must define this as a command API for an existing meeting session, not a competing lifecycle API. Evidence: E10, E11. Severity: 4. Detection: 4. Priority: 16.
7. **Client-side mention/action parsing is not sufficient for a durable command contract**: the frontend currently extracts mentions and requests object action plans before dispatch, while the backend chat setup only preserves `meeting_command` in event payload; the server must canonicalize mentions, object refs, and requested action before accepting a command ledger row. Evidence: E1, E12. Severity: 5. Detection: 4. Priority: 20.
8. **No implementation currently exists for `MeetingCommandEnvelope` or `MeetingCommandStore`**: repository search finds these names only in planning documents, so P0 must include model, store, route, and graph join implementation, not only UI changes. Evidence: E13. Severity: 5. Detection: 5. Priority: 25.

## 2. Evidence

E1. `handleSubmitCommand` in `AOLMeetingBottomShell` constructs `meetingActionParams` with `meeting_id`, `meeting_session_id`, `thread_id`, `meeting_command`, selected object fields, `meeting_mentions`, target refs, `object_action_entries`, and `object_action_plan`, then dispatches through object action invoke or `sendMessage`. Source: `web-console/src/components/capabilities/meeting-workbench/AOLMeetingBottomShell.tsx:L3909-L4007`.

E2. `MeetingSession` is a bounded governance session with status, agenda, decisions, traces, `action_items`, `minutes_md`, and metadata. Source: `backend/app/models/meeting_session.py:L32-L65`.

E3. `MeetingExecutionContext` captures executor runtime, auth state, budgets, recovery policy, route kind, execution profile, and runtime observability snapshot for a meeting. Source: `backend/app/models/meeting_execution_context.py:L22-L87`.

E4. `PipelineCore` reads explicit `meeting_session_id` or `meeting_id` from `action_params`, passes it into `ensure_meeting_session`, assembles `MeetingExecutionContext`, and runs `MeetingEngine`; dispatch orchestration and pack dispatch autofill `meeting_session_id` and `thread_id` into downstream inputs. Source: `backend/app/services/conversation/pipeline_core.py:L149-L197`, `backend/app/services/conversation/pipeline_core.py:L290-L352`, `backend/app/services/orchestration/dispatch_orchestrator.py:L601-L620`, `backend/app/services/orchestration/dispatch_orchestrator.py:L795-L820`, `backend/app/services/orchestration/pack_dispatch_adapter.py:L126-L134`.

E5. The selection runtime says actions are derived from object kind, relations, and meeting/materializer availability, not hard-coded per-screen button matrices. Source: `docs/core-architecture/addressable-object-layer/selection-and-contextual-action-runtime.md:L78-L81`.

E6. Generic verbs are already defined as `attach`, `recommend`, `expand`, `preview`, `stage`, `review`, and `promote`. Source: `docs/core-architecture/addressable-object-layer/meeting-attachment-and-materialization.md:L202-L222`.

E7. Meeting attachment docs say meetings should consume object references plus bounded projections and should not require pack-specific prompt glue or ad hoc UI-to-playbook bindings. Source: `docs/core-architecture/addressable-object-layer/meeting-attachment-and-materialization.md:L8-L27`.

E8. The object runtime model already defines `ObjectRef`, `ObjectAction`, `ObjectAffordanceCapability`, and object action closure records. Source: `backend/app/models/object_runtime.py:L111-L123`, `backend/app/models/object_runtime.py:L147-L157`, `backend/app/models/object_runtime.py:L202-L216`, `backend/app/models/object_runtime.py:L764-L790`.

E9. The meeting execution graph builder composes task nodes, relation proof nodes, fallback object nodes, artifact nodes, and edges into one graph response, but command nodes are currently derived from task/relation evidence rather than a command ledger store. Source: `backend/app/routes/core/workspace/meeting_graph.py:L500-L723`.

E10. Workspace sub-routers are mounted under `APIRouter(prefix="/api/v1/workspaces")`, and both `meeting_graph` and `object_runtime` are included there. Source: `backend/app/routes/core/workspace/__init__.py:L24-L40`.

E11. Meeting lifecycle routes are mounted separately under `/api/v1/workspaces/{workspace_id}/meeting-sessions`, while the execution graph route is already `/{workspace_id}/meetings/{meeting_id}/execution-graph`. Source: `backend/app/routes/meeting_sessions.py:L25-L28`, `backend/app/routes/core/workspace/meeting_graph.py:L846-L848`.

E12. Chat session setup derives `meeting_session_id` from action params and writes `meeting_command` into the user event payload, but it does not canonicalize command mentions or create a command ledger entry. Source: `backend/features/workspace/chat/streaming/chat_session_setup.py:L190-L224`.

E13. Repository search on 2026-05-02 with `rg -n "MeetingCommandStore|MeetingCommandEnvelope|/meetings/\\{meeting_id\\}/commands|command_ledger|commandLedger" /Users/shock/Projects_local/workspace/mindscape-ai-local-core /Users/shock/Projects_local/workspace/mindscape-ai-cloud/capabilities/ig` returned only planning-document references and no backend model/store/route implementation.

E14. `MeetingSessionStore` persists meeting sessions and decisions in PostgreSQL tables and ensures indexes for meeting session lookup; command persistence should follow this store pattern rather than overloading `MeetingSession.metadata`. Source: `backend/app/services/stores/meeting_session_store.py:L1-L6`, `backend/app/services/stores/meeting_session_store.py:L30-L79`, `backend/app/services/stores/meeting_session_store.py:L137-L160`.

## 3. Proposed changes

### Change 1: Introduce `MeetingCommandEnvelope`

Resolves Problems 1, 2, and 4.

- Add a shared model under `backend/app/models/meeting_command.py` or near `meeting_session.py`.
- P0 shape:

```python
class MeetingCommandEnvelope(BaseModel):
    workspace_id: Optional[str] = None
    meeting_id: str
    command_id: Optional[str] = None
    client_draft_id: Optional[str] = None
    origin_surface: str
    actor: Literal["user", "agent", "pack", "system"]
    intent_text: str
    context_objects: List[ObjectRoleEntry] = Field(default_factory=list)
    requested_action: Optional[MeetingRequestedAction] = None
    expected_outputs: List[str] = Field(default_factory=list)
    write_mode: Literal["recommendation_only", "proposal_only", "canonical_with_review"] = "recommendation_only"
    thread_id: Optional[str] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)
```

- The server should generate `command_id` when absent. `client_draft_id` is only an idempotency hint for optimistic UI drafts.
- The route path `workspace_id` is canonical. If a request body includes `workspace_id`, it must match the path or be rejected.
- `requested_action` should carry generic verb plus optional pack/playbook/affordance routing, not pack-private execution details.
- The envelope should be the backend contract for command bar submissions, mention-generated commands, and command templates inserted from UI surfaces.
- The accepted envelope must be server-canonical: backend parsing resolves `@owner.kind:id` mentions into `ObjectRef` / role entries, validates workspace ownership, and rejects malformed or unauthorized refs before persistence.

### Change 2: Add `POST /api/v1/workspaces/{workspace_id}/meetings/{meeting_id}/commands`

Resolves Problems 1, 2, 4, 5, 6, 7, and 8.

- Add a route that accepts `MeetingCommandEnvelope`, stamps workspace/session/thread identity, persists a command ledger entry, and then dispatches through existing runtime paths.
- The route should call existing object action planning/invocation or conversation dispatch; it should not replace runtime dispatch in P0.
- Insertion points:
  - meeting session model is at `backend/app/models/meeting_session.py:L32-L65`
  - meeting execution context exists at `backend/app/models/meeting_execution_context.py:L22-L87`
  - workspace-scoped routes are mounted by `backend/app/routes/core/workspace/__init__.py:L24-L40`
  - meeting execution graph route already uses `/{workspace_id}/meetings/{meeting_id}/execution-graph`
  - current UI dispatch envelope is in `AOLMeetingBottomShell.tsx:L3909-L4007`
- Add the paired read route `GET /api/v1/workspaces/{workspace_id}/meetings/{meeting_id}/commands` for command-ledger projection.
- Treat `meeting_id` as the existing `MeetingSession.id`; do not introduce a second meeting lifecycle namespace in P0.
- The UI should stop hand-building scattered `action_params` once this route exists.

### Change 3: Add `MeetingCommandStore`

Resolves Problems 2, 5, and 8.

- Persist one row per command envelope with:
  - `command_id`
  - `workspace_id`
  - `meeting_id`
  - `thread_id`
  - `origin_surface`
  - `actor`
  - `intent_text`
  - `context_objects`
  - `requested_action`
  - `status`
  - `created_at`
  - `updated_at`
  - `accepted_task_id` or execution pointer when available
- Implement the store next to `MeetingSessionStore`, using a dedicated `meeting_commands` table and indexes on `(workspace_id, meeting_id)`, `(workspace_id, thread_id)`, and `(command_id)`.
- Do not store the primary ledger in `MeetingSession.metadata`; metadata can keep derived summaries only.
- Event/task/artifact evidence remains separate, but the command ledger becomes the stable intentional spine.
- Meeting execution graph should prefer command ledger nodes, then attach task/relation/artifact proof to them. Relation-only recovery remains required for older sessions.

### Change 3A: Add server-side command grammar normalization

Resolves Problems 1, 4, and 7.

- Add a backend helper such as `backend/app/services/meeting_command_parser.py`.
- P0 grammar is intentionally small:
  - free text command
  - `@owner.kind:id` object mentions
  - optional slash verb such as `/stage`, `/review`, `/promote`
  - optional role hints such as `as source`, `for target`
- The parser should output:
  - normalized `intent_text`
  - `context_objects`
  - `requested_action.verb`
  - unresolved mentions with typed errors
- The route may accept client-provided `meeting_mentions`, but must treat them as hints and re-resolve them server-side.

### Change 4: Make command grammar the main UX; UI surfaces insert references and templates

Resolves Problems 3 and 4.

- Do not add broad action-button matrices to IG cards, PD rows, artifact cards, or review rows.
- UI surfaces should support:
  - insert mention/reference into the active command
  - pin object into session context
  - offer command templates, for example `/stage @ig.reference:ref_123 for @pd.scene:sc01`
  - optionally expose a small icon for "insert mention" or "open detail"
- The command bar remains the main work entrypoint.
- The canonical operation is not "button clicked"; it is "structured command envelope submitted".

### Change 5: Project the command ledger into the canvas

Resolves Problems 2 and 5.

- `AOLCanvasProjection` should read the command ledger and produce `CommandEntry[]`.
- The center canvas should use selected command id to find related execution graph edges, events, artifacts, and object relation proof.
- `meeting_graph.py` should accept the command store as an additional input, create command nodes from ledger rows first, and then attach existing task/relation/artifact proof by `command_id`, `action_plan_id`, task id, or degraded fallback metadata.
- The command ledger should render command phases and statuses:
  - drafted
  - accepted
  - running
  - completed
  - failed
  - superseded
- Raw meeting events remain an audit trail, not the primary command source.
- Backend graph projection must emit UI-compatible statuses while preserving raw lifecycle state in metadata; the current implementation maps durable command lifecycle to graph status and keeps `ledger_status`.
- The Meeting Workbench view should refresh command-ledger projection from the shared workspace SSE stream when active meeting/session runtime events arrive; a dedicated command-ledger event stream is optional unless product UX latency or scale demands it.

## 4. Verification SOP

1. **Envelope API accepts command grammar with object references**
   - Command: `curl -sS -X POST "http://127.0.0.1:8300/api/v1/workspaces/{workspace_id}/meetings/{meeting_id}/commands" -H "Content-Type: application/json" -d @/tmp/meeting-command-envelope.json | jq '.command_id, .status'`
   - Expected true: response contains a stable `command_id` and accepted/running status.
   - Fail false: route requires UI-only `action_params` or loses context objects.
   - Proves: Problems 1, 2, and 4.

2. **Command ledger persists independently of event projection**
   - Command: `curl -sS "http://127.0.0.1:8300/api/v1/workspaces/{workspace_id}/meetings/{meeting_id}/commands" | jq '.commands[0] | {command_id, origin_surface, intent_text, context_objects}'`
   - Expected true: persisted command records include origin surface, text, and role-bearing refs.
   - Fail false: commands can only be reconstructed from generic events.
   - Proves: Problems 2 and 5.

3. **Existing command bar dispatch goes through envelope route**
   - Manual path: open an AOL meeting, type a command using at least one `@` mention, submit it, and inspect network calls.
   - Expected true: the first write call is `/meetings/{meeting_id}/commands`; runtime dispatch happens after command acceptance.
   - Fail false: UI still dispatches directly through scattered `sendMessage(action_params)` without recording a command envelope.
   - Proves: Problems 1 and 4.

4. **UI surfaces insert mentions rather than executing hidden actions**
   - Manual path: click an IG reference card "insert mention" affordance or select the card while the command bar is active.
   - Expected true: command bar receives a structured mention/chip; no hidden playbook dispatch starts.
   - Fail false: clicking a card directly starts a pack run without creating a command envelope.
   - Proves: Problem 3.

5. **Execution graph prefers command ledger identity**
   - Command: `curl -sS "http://127.0.0.1:8300/api/v1/workspaces/{workspace_id}/meetings/{meeting_id}/execution-graph?limit=200" | jq '.nodes[] | select(.kind=="command") | .metadata.command_id'`
   - Expected true: new command nodes contain `command_id`; older sessions still render relation-only fallback nodes.
   - Fail false: new commands have no durable id or older relation-only proof disappears.
   - Proves: Problem 5.

6. **Server rejects malformed or cross-workspace mentions**
   - Command: `curl -sS -X POST "http://127.0.0.1:8300/api/v1/workspaces/{workspace_id}/meetings/{meeting_id}/commands" -H "Content-Type: application/json" -d @/tmp/meeting-command-invalid-ref.json | jq '.detail.code'`
   - Expected true: response is a typed 4xx error such as `invalid_command_reference` or `object_not_found`.
   - Fail false: malformed client-supplied mentions are persisted or dispatched.
   - Proves: Problem 7.

7. **Route naming does not fork meeting lifecycle**
   - Command: `curl -sS "http://127.0.0.1:8300/api/v1/workspaces/{workspace_id}/meeting-sessions/{meeting_id}" | jq '.id'`
   - Expected true: the same session id used by `/meetings/{meeting_id}/commands` resolves through the existing meeting-session lifecycle route.
   - Fail false: `/meetings/{meeting_id}/commands` creates a separate lifecycle object.
   - Proves: Problem 6.

## 5. Automated test plan

1. Add backend tests for the new command model and route.
   - Target: `backend/tests/test_meeting_command_envelope.py`.
   - Scenario: submit envelope with `@object`-derived refs, origin surface, requested verb, and write mode.
   - Assertions: command persists, ids are stable, context objects survive round trip, malformed refs return typed errors.
   - Prevents regressions for Problems 1, 2, and 4.

2. Add backend graph integration tests.
   - Target: `backend/tests/test_meeting_execution_graph_commands.py`.
   - Scenario: command ledger row plus task/artifact/relation proof.
   - Assertions: execution graph emits command node keyed by `command_id`, links to run/artifact/provenance, and preserves relation-only fallback for older sessions.
   - Prevents regressions for Problem 5.

3. Add parser and validation tests.
   - Target: `backend/tests/test_meeting_command_parser.py`.
   - Scenario: parse `/stage @ig.reference:ref_123 as source for @pd.scene:sc01`, malformed refs, duplicate refs, and unresolved refs.
   - Assertions: normalized role-bearing refs are produced; invalid refs return typed errors; no client-only mention payload is trusted without resolution.
   - Prevents regressions for Problems 4 and 7.

4. Add frontend command bar tests.
   - Target: `web-console/src/components/capabilities/meeting-workbench/MeetingCommandBar.spec.tsx` or the migrated workbench spec.
   - Scenario: typing `/stage @ig.reference:ref_123 for @pd.scene:sc01` with mention chips.
   - Assertions: UI posts `MeetingCommandEnvelope`, not ad hoc `sendMessage(action_params)`.
   - Prevents regressions for Problems 1, 3, and 4.

5. Add surface mention insertion tests.
   - Target: pack-owned UI tests for IG reference card and PD scene row.
   - Scenario: click "insert mention" from a card while command bar is active.
   - Assertions: mention inserted; no runtime dispatch; command submit later creates envelope.
   - Prevents regressions for Problem 3.

## 6. Risks / open questions

1. **Migration of existing sessions**: older meetings lack command ledger rows. Execution graph must keep relation/task/event fallback.
2. **Command grammar must stay small**: P0 should support command text plus structured refs and generic verbs, not a full DSL.
3. **Duplicate dispatch risk**: introducing `/commands` can double-run if the UI also calls `sendMessage`; object-action, selected playbook, and ordinary chat/runtime commands now have explicit route ownership, and the command-submit fallback to direct runtime calls has been removed.
4. **Agent-authored commands need actor semantics**: `actor=agent` should be allowed, but agent-inserted commands may need review gates before execution.
5. **Store location is open**: use the existing store pattern for meeting sessions/events/tasks, but do not overload `MeetingSession.metadata` for the primary ledger.
6. **Command id join may be incomplete in early runtime tasks**: P0 carries `command_id` through command metadata, object action plan/invoke metadata, and task status sync paths, but older runtime tasks can still fall back to weaker `action_plan_id` matching.
7. **API versioning risk**: route names must keep compatibility with existing `/meeting-sessions` lifecycle endpoints and existing `/meetings/{meeting_id}/execution-graph` projections.
8. **Event precision risk**: Meeting Workbench now refreshes from the shared workspace SSE stream for active meeting events; add a dedicated command-ledger event stream only if the shared stream produces too much reload noise or misses command lifecycle transitions in real workloads.
