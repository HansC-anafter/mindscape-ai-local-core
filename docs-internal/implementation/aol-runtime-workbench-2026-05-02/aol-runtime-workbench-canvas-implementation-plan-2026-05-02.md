# AOL Runtime Workbench Canvas Implementation Plan

## 1. Problem list

1. **The current meeting graph shell is a proof viewer, not an integrated workbench canvas**: `AOLMeetingBottomShell` projects runtime data into fixed lanes, but it does not expose a Blender-style synchronized editor model where object selection, command history, properties, and outcomes share one runtime state. Evidence: E1, E2, E3. Severity: 5. Detection: 4. Priority: 20.
2. **Graph UI semantics are too low-level for user work**: the canvas lanes are `Context`, `Object Graph`, `Commands`, `Runs`, `Outputs`, `Artifacts`, and `Next`, which classify implementation data instead of answering what object is active, what command is being worked, what outcome was produced, and what next action is available. Evidence: E4, E5, E6. Severity: 5. Detection: 3. Priority: 15.
3. **The graph canvas does not yet act as a projection composition layer**: local-core already owns selection state, meeting attachment, graph projection, and runtime catalog APIs, while packs own resolvers and materializers, but the frontend shell still merges data directly in one component instead of building a reusable canvas projection model. Evidence: E1, E2, E7. Severity: 4. Detection: 4. Priority: 16.
4. **Object relations and execution proof are not rendered as coordinated editors**: execution graph, object graph, trace, artifacts, and command state are available as separate data streams, but the UI does not present an outliner, semantic flow, inspector, and command ledger that all track the same selection. Evidence: E5, E8, E9. Severity: 4. Detection: 3. Priority: 12.
5. **The current design risks expanding the fixed-lane board instead of converging on a runtime editor framework**: graph-specific docs already say follow-on work is object-aware taxonomy, projection caching, expansion heuristics, and subgraph contracts; adding more cards to the existing lane layout will not create that framework. Evidence: E3, E6. Severity: 4. Detection: 3. Priority: 12.
6. **The current implementation is concentrated in one large component**: `AOLMeetingBottomShell.tsx` contains the projection merge, toolbar, canvas, inspector, command bar, and dispatch logic; a product workbench should not add more behavior to that file without extracting projection and editor modules. Evidence: E5, E11. Severity: 4. Detection: 4. Priority: 16.
7. **The canvas plan depends on a command ledger that is not implemented yet**: `AOLCanvasProjection.commandLedger` cannot be authoritative until the command-envelope plan adds the backend model, store, and routes; the canvas must define a fallback mode for legacy sessions and a hard dependency for full P0 completion. Evidence: E12. Severity: 5. Detection: 5. Priority: 25.

## 2. Evidence

E1. The AOL architecture defines local-core as owner of selection state, contextual launch surfaces, meeting attachment, graph projection, and runtime catalog APIs, while capability packs own canonical schemas, business rules, storage, and object-specific resolvers/materializers. Source: `docs/core-architecture/addressable-object-layer/README.md:L18-L25`.

E2. The same README defines `Projection` as a runtime view such as graph, toolbar popover, meeting context, or review lane, and `Materializer` as pack-owned code that converts meeting results into proposals, previews, handoffs, or canonical writeback. Source: `docs/core-architecture/addressable-object-layer/README.md:L46-L52`.

E3. Graph surfaces are explicitly projections, not canonical object truth, and should consume `ObjectRef`, summaries, relations, lineage pointers, execution metadata, and review metadata. Source: `docs/core-architecture/addressable-object-layer/graph-and-projection-surfaces.md:L8-L33`.

E4. `AOLMeetingBottomShell` declares the current fixed graph lanes as `Context`, `Object Graph`, `Commands`, `Runs`, `Outputs`, `Artifacts`, and `Next`. Source: `web-console/src/components/capabilities/meeting-workbench/AOLMeetingBottomShell.tsx:L238-L245`.

E5. `projectMeetingGraph` directly receives events, artifacts, local tasks, object graph nodes, execution graph nodes, and execution graph edges, then merges them into one `MeetingGraphProjection`. Source: `web-console/src/components/capabilities/meeting-workbench/AOLMeetingBottomShell.tsx:L1073-L1229`.

E6. Graph-specific guidance says the current execution graph should evolve from execution-centric graph into an object-aware projection layer, and runtime graph-aware surfaces should converge on `/object-graph/project` as the shared normalization lane. Source: `docs/core-architecture/addressable-object-layer/graph-and-projection-surfaces.md:L40-L52`.

E7. The object runtime model already has shared transport and operation primitives: `ObjectRef`, `ObjectAction`, `ObjectGraphProjectionCapabilities`, and `ObjectAffordanceCapability`. Source: `backend/app/models/object_runtime.py:L111-L123`, `backend/app/models/object_runtime.py:L147-L157`, `backend/app/models/object_runtime.py:L192-L216`.

E8. The meeting execution graph route exposes normalized nodes and edges with `kind`, `lane`, `metadata`, and degraded state. Source: `backend/app/routes/core/workspace/meeting_graph.py:L27-L69`.

E9. The execution graph builder composes tasks, object relation records, fallback object nodes, provenance nodes, artifact nodes, and edges into one `MeetingExecutionGraphResponse`. Source: `backend/app/routes/core/workspace/meeting_graph.py:L500-L723`.

E10. Follow-on graph work is already identified as object-aware node taxonomy, projection caching rules, graph expansion heuristics, and graph traversal/subgraph request contracts. Source: `docs/core-architecture/addressable-object-layer/graph-and-projection-surfaces.md:L64-L69`.

E11. `AOLMeetingBottomShell.tsx` is 4181 lines as of 2026-05-02 (`wc -l /Users/shock/Projects_local/workspace/mindscape-ai-local-core/web-console/src/components/capabilities/meeting-workbench/AOLMeetingBottomShell.tsx`), which confirms the current implementation is already a high-risk aggregation point for unrelated responsibilities.

E12. Repository search on 2026-05-02 with `rg -n "MeetingCommandStore|MeetingCommandEnvelope|/meetings/\\{meeting_id\\}/commands|command_ledger|commandLedger"` found only planning-document references and no implemented command model/store/route.

E13. The product UX/UI layout plan defines `AOL Runtime Shell` as the shared host/integration framework, `AOL Runtime Workbench` as the user-facing product surface, `Meeting Workbench` as the meeting-session view, and the Command Ledger as the intent spine; it also defines a meeting-centered view with context bar, object outliner, semantic flow canvas, inspector, command dock, and command ledger. Source: `docs-internal/implementation/aol-runtime-workbench-2026-05-02/aol-runtime-workbench-product-ux-ui-layout-implementation-plan-2026-05-02.md:L13-L79`, `docs-internal/implementation/aol-runtime-workbench-2026-05-02/aol-runtime-workbench-product-ux-ui-layout-implementation-plan-2026-05-02.md:L140-L177`.

## 3. Proposed changes

### Change 1: Rename the architecture/product target from meeting graph to AOL Runtime Shell / AOL Runtime Workbench / Meeting Workbench

Resolves Problems 1 and 2.

- Keep `Meeting Graph` as an internal/runtime/debug concept, make the shared host framework `AOL Runtime Shell`, make the user-facing product surface `AOL Runtime Workbench`, and make the meeting-session view `Meeting Workbench`.
- The product story becomes: selected object -> role-bearing context -> guidance/next step -> command/operator -> runtime run -> output/proposal/artifact -> provenance -> review or next command.
- The shell should stop presenting fixed lanes as the primary mental model. Lanes can remain a debug or trace view, but the primary canvas should answer "what am I working on, what changed, and what can I do next?"
- Verified insertion point: the visible pane title is owned by `AddressableObjectHostShell.tsx` and the internal lane layout is owned by `AOLMeetingBottomShell.tsx:L238-L245`.

### Change 2: Add `AOLCanvasProjection` as the frontend composition model

Resolves Problems 1, 3, and 4.

- Create a projection builder, for example `web-console/src/components/capabilities/meeting-workbench/aolCanvasProjection.ts`.
- Inputs:
  - active meeting session and attachments
  - selected `ObjectRef`
  - `/object-graph/project`
  - `/meetings/{meeting_id}/execution-graph`
  - `/meetings/{meeting_id}/commands` once the command envelope plan is implemented
  - meeting events
  - meeting artifacts
  - object actions and materializer routes when available
- Output:

```ts
type AOLCanvasProjection = {
  focusObject: CanvasObject | null;
  sessionObjects: CanvasObject[];
  semanticFlow: CanvasNode[];
  semanticEdges: CanvasEdge[];
  guidanceState: GuidanceState | null;
  guidanceNodes: CanvasNode[];
  commandLedger: CommandEntry[];
  availableActions: RuntimeAction[];
  reviewRoutes: ReviewRoute[];
  traceEvents: MeetingEventSummary[];
  degradedEvidence: DegradedEvidence[];
};
```

- This projection is not a new source of truth. It is a UI projection over existing runtime data, aligned with the graph surface rule in E3.
- P0 must support two modes:
  - full mode: command ledger API present, `commandLedger` comes from backend command rows
  - legacy mode: command entries are degraded projections inferred from execution graph/events, marked with `source: "legacy_inferred"`
- Full product acceptance requires full mode. Legacy mode is only for older sessions and migration safety.

### Change 3: Replace the fixed lane board with synchronized editors

Resolves Problems 2 and 4.

- Introduce coordinated UI regions:
  - top `ContextBar`: focus, role, status, runtime, next-step, and missing-context chips
  - left `ObjectOutliner`: session objects grouped by role (`target`, `source`, `evidence`, `constraint`, `output`, `review`) plus missing-role placeholders
  - center `SemanticFlowCanvas`: selected object, selected guidance, or selected command impact subgraph
  - right `PropertiesInspector`: summary, guidance, actions, relations, runtime, and advanced raw trace
  - bottom `CommandDock` and `CommandLedger`: command input, templates, accepted/running/completed/failed commands, and generated follow-up prompts
- Selection state should be shared. Selecting an object in the outliner changes the canvas focus and inspector. Selecting a command in the ledger changes the canvas to the impact chain. Selecting an artifact shows provenance and review routes.
- Keep raw trace and current lane board available as secondary/debug views.
- Implement these as separate modules rather than expanding `AOLMeetingBottomShell.tsx`:
  - `aolCanvasProjection.ts`
  - `AOLRuntimeShell.tsx`
  - `AOLRuntimeShellProvider.tsx` or equivalent provider/hook/store boundary
  - `AOLRuntimeWorkbench.tsx`
  - `MeetingWorkbenchView.tsx`
  - `ObjectOutliner.tsx`
  - `SemanticFlowCanvas.tsx`
  - `PropertiesInspector.tsx`
  - `CommandLedger.tsx`
  - `CommandDock.tsx`
- Keep `AOLMeetingBottomShell.tsx` as a compatibility wrapper during migration, then shrink it to orchestration and data loading only.

### Change 4: Render selected subgraphs rather than the full global graph

Resolves Problems 2, 4, and 5.

- Default canvas scope:
  - selected object: object neighborhood + guidance + current meeting edges
  - selected guidance: guidance -> required context -> command template -> next
  - selected command: command -> run -> output/artifact/provenance chain
  - no selection: concise meeting summary graph with current focus and recommended next step
- Do not render every trace event or every edge by default.
- Use degraded nodes when join identifiers are missing, rather than silently dropping evidence. This aligns with the existing meeting graph proof rules in `full-product-semantics.md:L95-L98`.

### Change 5: Keep pack-specific semantics out of local-core canvas primitives

Resolves Problems 3 and 5.

- Local-core canvas node taxonomy should be generic:
  - `object`
  - `guidance`
  - `command`
  - `run`
  - `outcome`
  - `artifact`
  - `proposal`
  - `review_route`
  - `next`
  - `blocked`
  - `provenance`
- Pack-owned guidance must project into generic `guidance`, `next`, or `blocked` canvas nodes and may also render details inside Inspector; local-core should only pass bounded projections and refs.
- The host shell must not encode IG, PD, character, or MMS semantics directly.

### Change 6: Gate rollout by backend command-ledger readiness

Resolves Problems 6 and 7.

- Phase 0 can extract `aolCanvasProjection.ts` and render legacy inferred command entries, but must label them as degraded.
- Phase 1 implements command envelope/store/route and switches `commandLedger` to backend rows.
- Phase 2 replaces the fixed lane board as the default Work view and leaves lanes under Debug.
- Do not declare the workbench product-ready until Phase 1 is complete, because the meeting cannot be the central collaboration platform without durable command identity.

## 4. Verification SOP

1. **Projection builder unit check**
   - Command: `cd /Users/shock/Projects_local/workspace/mindscape-ai-local-core/web-console && npx vitest run src/components/capabilities/meeting-workbench/aolCanvasProjection.test.ts --environment jsdom`
   - Expected true: a fixture containing focus object, command, run, relation, artifact, and review route produces `focusObject`, grouped `sessionObjects`, a selected `semanticFlow`, and a command ledger.
   - Fail false: projection output is just the old lane array or drops degraded evidence.
   - Proves: Problems 1, 3, and 4.

2. **Canvas editor synchronization**
   - Command: `cd /Users/shock/Projects_local/workspace/mindscape-ai-local-core/web-console && npx vitest run src/components/capabilities/meeting-workbench/AOLRuntimeWorkbench.spec.tsx --environment jsdom`
   - Expected true: selecting an object in the outliner changes center canvas and inspector; selecting a command in ledger changes center canvas to the impact chain.
   - Fail false: editors keep independent selection state or raw trace is the only available detail.
   - Proves: Problems 2 and 4.

3. **No pack-specific local-core semantics**
   - Command: `cd /Users/shock/Projects_local/workspace/mindscape-ai-local-core && rg -n "ig\\.reference|performance_direction|storyboard_scene|character_card|generated_reels_asset" web-console/src/components/capabilities/meeting-workbench`
   - Expected true: no pack-specific labels or fallback object kinds appear in generic workbench components, except neutral test fixtures explicitly named as such.
   - Fail false: local-core canvas contains pack-owned semantics.
   - Proves: Problem 5.

4. **Runtime projection still uses existing APIs**
   - Command: `curl -sS "http://127.0.0.1:8300/api/v1/workspaces/{workspace_id}/meetings/{meeting_id}/execution-graph?limit=200" | jq '.nodes | length, .edges | length'`
   - Expected true: the workbench can render from the existing execution graph response without requiring a new canonical graph store.
   - Fail false: the UI requires a second canonical graph payload before it can render.
   - Proves: Problems 3 and 5.

5. **Browser acceptance smoke**
   - Command: `cd /Users/shock/Projects_local/workspace/mindscape-ai-local-core && .venv/bin/python scripts/e2e/pd_ux_aol_acceptance.py`
   - Expected true: S0-S9 remains passed after the UI composition change; S7 still posts a real meeting command and finds persisted runtime output.
   - Fail false: runtime output lands but the workbench cannot project it, or workbench projection works only with mocked data.
   - Proves: Problems 1 through 4 across the real runtime path.

6. **Component extraction check**
   - Command: `cd /Users/shock/Projects_local/workspace/mindscape-ai-local-core && rg --files web-console/src/components/capabilities/meeting-workbench | rg "aolCanvasProjection|AOLRuntimeWorkbench|ObjectOutliner|SemanticFlowCanvas|PropertiesInspector|CommandLedger|CommandDock"`
   - Expected true: projection and editor modules exist outside `AOLMeetingBottomShell.tsx`.
   - Fail false: the workbench is implemented by adding more logic to the existing 4181-line shell file.
   - Proves: Problem 6.

7. **Legacy vs full command-ledger mode**
   - Command: `cd /Users/shock/Projects_local/workspace/mindscape-ai-local-core/web-console && npx vitest run src/components/capabilities/meeting-workbench/aolCanvasProjection.test.ts --environment jsdom`
   - Expected true: fixtures cover both backend command-ledger rows and legacy inferred command entries, and the legacy entries are flagged as degraded.
   - Fail false: inferred commands look authoritative or backend ledger rows are ignored.
   - Proves: Problem 7.

## 5. Automated test plan

1. Add `web-console/src/components/capabilities/meeting-workbench/aolCanvasProjection.test.ts`.
   - Scenario: merge execution graph, object graph projection, meeting events, artifacts, and attach metadata.
   - Assertions: roles are grouped into `sessionObjects`; selected command produces a bounded impact chain; degraded evidence is preserved; raw trace stays available but not primary.
   - Prevents regressions for Problems 1, 3, and 4.

2. Add `web-console/src/components/capabilities/meeting-workbench/AOLRuntimeWorkbench.spec.tsx`.
   - Scenario: render outliner, center semantic canvas, properties inspector, and command ledger from one projection.
   - Assertions: all editors reflect the same selected object/command; no editor owns separate canonical state.
   - Prevents regressions for Problems 2 and 4.

3. Keep `AOLMeetingBottomShell.spec.tsx` as a compatibility wrapper suite during migration.
   - Scenario: old entrypoint still opens the new workbench canvas and can switch to trace/debug lanes.
   - Assertions: existing meeting attach, session switcher, command dispatch, and inspector rail continue to work.
   - Prevents regressions for Problems 1 and 5.

4. Add a no-pack-semantics grep test under the web-console test suite or CI script.
   - Scenario: generic meeting-workbench components do not hard-code IG/PD object kinds.
   - Assertions: pack-owned labels appear only in pack-owned fixtures or installed pack payloads.
   - Prevents regressions for Problem 5.

5. Add an extraction boundary test.
   - Scenario: render `AOLRuntimeWorkbench` with mocked projection data and verify `AOLMeetingBottomShell` only wires data/loading callbacks.
   - Assertions: projection merge logic lives in `aolCanvasProjection.ts`; editor selection state is managed by the new workbench component; old fixed lanes are reachable only through Debug.
   - Prevents regressions for Problems 6 and 7.

## 6. Risks / open questions

1. **Projection model can become too broad**: `AOLCanvasProjection` must remain a UI projection, not a persistence model.
2. **Large sessions may require projection caching**: graph docs already list projection caching and expansion heuristics as follow-on work; the first implementation should keep selected subgraphs small.
3. **Legacy bottom-shell tests may overfit to lanes**: migrate tests toward semantic editors while preserving a debug lane fallback.
4. **Pack guidance needs a clear slot contract**: local-core should define where pack-owned guidance renders, but not what IG/PD guidance means.
5. **Browser layout risk**: the new four-editor workbench must be tested at the same bottom-pane heights as the current shell, especially compact and expanded modes.
6. **Command ledger dependency**: without the backend command-ledger API, the workbench can only show inferred command state; do not call that final product behavior.
7. **Monolith regression risk**: any implementation that grows `AOLMeetingBottomShell.tsx` instead of extracting modules should be rejected before review.
