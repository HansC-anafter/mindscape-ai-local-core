# Meeting Command Ledger And Impact Graph Implementation Plan

## 1. Problem list

1. **Command visibility is present but not yet a first-class ledger**: the Flow panel has a `commands` lane, but command nodes only project as generic user intent, so the user cannot quickly distinguish initial commands from inserted commands or inspect the full effect of a command. Evidence: E1, E2, E6. Severity: 4. Detection: 3. Priority: 12.
2. **Runtime impact is not modeled as a selected-command chain**: execution graph responses can contain edges, but the current UI projection returns only nodes and counts; the Flow canvas therefore cannot selectively highlight `command -> round -> decision -> action -> artifact -> minutes` without additional relation state. Evidence: E3, E4, E6. Severity: 4. Detection: 4. Priority: 16.
3. **Inspector defaults expose raw trace before user-facing impact**: the current inspector has a Trace tab that lists raw replay events and JSON, while the Graph tab is object-relation oriented; there is no dedicated command impact summary with original command, runtime route, resulting decisions, action items, artifacts, and minutes. Evidence: E5, E6. Severity: 3. Detection: 3. Priority: 9.
4. **Trackpad scroll can conflict with graph zoom and card overflow browsing**: the meeting task canvas owns wheel zoom and node lanes contain overflow scroll areas, so wheel handling must explicitly avoid trackpad-like scroll and node/lane scroll targets. Evidence: E7, E8. Severity: 4. Detection: 2. Priority: 8.
5. **Host shell must not synthesize pack-owned object refs from raw tokens**: generic AOL meeting UX must resolve object/scene/character references from the registry, not from local-core hardcoded pack guesses. Evidence: E9. Severity: 4. Detection: 4. Priority: 16.

## 2. Evidence

E1. `GRAPH_LANES` declares `commands` as a first-class Flow lane; the P0 implementation frames it as `Issued instructions`, so command history remains visible in Flow instead of being buried in Trace. Source: `web-console/src/components/capabilities/meeting-workbench/AOLMeetingBottomShell.tsx:L238-L246`.

E2. `buildMeetingEventNode` maps `actor === 'user'` into `kind: 'command'` and `lane: 'commands'`; meeting lifecycle and decision events are filtered out of the normal flow projection. Source: `web-console/src/components/capabilities/meeting-workbench/AOLMeetingBottomShell.tsx:L946-L1035`.

E3. `MeetingGraphProjection` now carries `nodes`, `edges`, trace counts, and event counts; command impact is derived from the selected command rather than stored as a new canonical graph. Source: `web-console/src/components/capabilities/meeting-workbench/AOLMeetingBottomShell.tsx:L190-L197`.

E4. `MeetingExecutionGraphPayload` accepts `edges`, and the implementation must keep those edges available to command-impact derivation instead of reducing the payload to node-only lanes. Sources: `web-console/src/components/capabilities/meeting-workbench/AOLMeetingBottomShell.tsx:L199-L205`, `web-console/src/components/capabilities/meeting-workbench/AOLMeetingBottomShell.tsx:L1073-L1230`.

E5. The inspector has Trace and Graph tabs. Graph is object-neighborhood oriented; command-impact details must be scoped and visibly labeled so Graph does not mean both object graph and command impact. Source: `web-console/src/components/capabilities/meeting-workbench/AOLMeetingBottomShell.tsx:L2546-L2915`.

E6. Existing AOL graph architecture says graph surfaces are projections, not canonical owners, and graph expansion should consume runtime projections and object graph normalization lanes. Source: `docs/core-architecture/addressable-object-layer/graph-and-projection-surfaces.md:L40-L52`.

E7. `MeetingTaskCanvas` owns pointer pan and wheel zoom at the canvas level. Source: `web-console/src/components/capabilities/meeting-workbench/AOLMeetingBottomShell.tsx:L2070-L2190`.

E8. Lane content is an overflow scroll region and node cards are clickable child surfaces. The current P0 patch marks lane scroll regions and guards zoom against node/lane targets. Sources: `web-console/src/components/capabilities/meeting-workbench/AOLMeetingBottomShell.tsx:L272-L284`, `web-console/src/components/capabilities/meeting-workbench/AOLMeetingBottomShell.tsx:L2256-L2256`.

E9. Manual mention fallback now only resolves host-native raw tokens (`@object`, `@pack`, `@session`, `@node`), while selected registry mentions are cached as resolved refs and unresolved pack-owned raw tokens are covered by a regression test that proves they do not synthesize `performance_direction` or `character_training` object refs. Sources: `web-console/src/components/capabilities/meeting-workbench/AOLMeetingBottomShell.tsx:L1305-L1357`, `web-console/src/components/capabilities/meeting-workbench/AOLMeetingBottomShell.tsx:L2267-L2306`, `web-console/src/components/capabilities/meeting-workbench/AOLMeetingBottomShell.spec.tsx:L1018-L1065`.

## 3. Proposed changes

### Change 1: Rename and enrich the Commands lane as a command ledger

Resolves Problem 1.

- Update lane copy from `Commands / User intent` to a command-ledger framing, for example `Commands / Issued instructions`.
- Add node fields or derived display props for:
  - command sequence number
  - command phase: `initial`, `inserted`, `follow-up`
  - accepted / running / completed / failed / superseded status
  - command timestamp and actor
  - attached object role summary
- Keep the lane in Flow mode as the main user entry point; do not move command history into Trace.
- Verified insertion points: `GRAPH_LANES` at `AOLMeetingBottomShell.tsx:L212-L219`; user-event command projection at `AOLMeetingBottomShell.tsx:L776-L846`.

### Change 2: Add command impact relation state without rendering global line noise

Resolves Problem 2.

- Extend `MeetingGraphProjection` with canonical execution `edges`; keep selected-command state outside the projection and derive `MeetingCommandImpact` from the selected command.
- Consume `MeetingExecutionGraphPayload.edges` into frontend state; this is a hard gate because backend already emits command, runtime, object, output, artifact, and event-chain edges.
- Build selected-command impact from execution graph edges when available and from trace event order as fallback.
- Do not render all impact edges by default.
- When a command node is selected, highlight only nodes and edges reachable from that command:
  - command
  - meeting start / round
  - planner or runtime turn
  - decision proposal / final decision
  - action item
  - artifact / minutes / memory writeback
- Keep non-selected nodes visible but visually muted.
- Events that are hidden from the default Flow projection (`meeting_start`, `meeting_round`, `decision_*`, `meeting_end`) must still be available as selected-command impact milestones, either as lightweight auxiliary nodes or as rows inside the command impact inspector.
- Verified insertion points: projection shape at `AOLMeetingBottomShell.tsx:L190-L197`; execution graph payload at `AOLMeetingBottomShell.tsx:L199-L205`; node merge path at `AOLMeetingBottomShell.tsx:L1073-L1230`.

### Change 3: Add a command impact drawer in the inspector

Resolves Problems 1 and 3.

- When selected node kind is `command`, show a command-first inspector view before raw trace.
- Required P0 fields:
  - original command text
  - command source: initial or inserted
  - derived status
  - execution edge count
  - produced decision count
  - action item count
  - output count
  - artifact count
  - reachable node list
- P1 fields, when backend metadata is present:
  - meeting id / event id / thread id
  - attached objects and roles
  - runtime route and bridge state at dispatch time
  - minutes and memory writeback evidence
- Keep Raw Trace as a secondary section or tab.
- Verified insertion point: `MeetingInspectorPanel` at `AOLMeetingBottomShell.tsx:L2353-L2690`.

### Change 4: Make Graph mode a local impact graph, not the default command view

Resolves Problems 2 and 3.

- Flow remains the chronological surface.
- The current Graph tab remains object-neighborhood scoped and must be labeled as bounded object graph.
- Command impact is exposed first through selected-command highlighting in Flow plus a labeled command-impact inspector. A later visual edge renderer may add command-impact graph lines, but it must not replace the command ledger as the main entry point.
- Preserve current object-neighborhood behavior by labeling it separately from command impact. The implementation must not reuse `Graph` to mean both object graph and command impact without a visible scope label.
- Default graph scope:
  - selected command: Flow impact highlight plus command-impact inspector
  - selected object: object neighborhood graph
  - no selection: meeting summary graph
- Use runtime projection data and object graph projection data only; do not introduce a new canonical graph owner.
- This follows the existing projection rule in `graph-and-projection-surfaces.md:L40-L52`.

### Change 5: Preserve trackpad scroll and node overflow behavior

Resolves Problem 4.

- Keep the P0 guard in `shouldZoomMeetingCanvasFromWheel`.
- Zoom only when a wheel event looks like a discrete mouse wheel and is not inside a node card or lane scroll region.
- Do not call `preventDefault()` for ignored wheel events; this lets trackpad scroll and overflow regions work normally.
- Verified insertion points: `AOLMeetingBottomShell.tsx:L246-L260`, `AOLMeetingBottomShell.tsx:L1984-L1990`, `AOLMeetingBottomShell.tsx:L2081-L2085`.

### Change 6: Keep host-shell UX fixtures neutral and route object refs through registry resolution

Resolves Problem 5.

- New command-impact and object-graph tests must use neutral fixture data such as `fixture_pack`, `generic_object`, `generated_asset`, and `fixture_runtime`.
- New host-shell tests must not assert pack-specific labels like `performance_direction`, `character_training`, `generated_reels_asset`, or `visual_audit` unless the test is explicitly covering an existing legacy path.
- Manual raw mention fallback must not synthesize pack-owned object refs. Object/scene/character references must come from selected registry completion items or the current selected object.
- Selected registry mentions must be cached while the command is being composed so clearing the live completion query does not force local-core to guess owner packs from token text.
- Pack-owned behavior must be tested in pack-owned tests or deploy-pack acceptance, not in generic local-core host-shell UX tests.
- Verified insertion points: raw mention fallback at `AOLMeetingBottomShell.tsx:L1305-L1357`; selected mention cache at `AOLMeetingBottomShell.tsx:L2267-L2306`; regression spec at `AOLMeetingBottomShell.spec.tsx:L1018-L1065`.

## 4. Verification SOP

1. **Command ledger visibility**
   - Command: `cd /Users/shock/Projects_local/workspace/mindscape-ai-local-core/web-console && npx vitest run src/components/capabilities/meeting-workbench/AOLMeetingBottomShell.spec.tsx --environment jsdom`
   - Expected true: command nodes render in the Commands lane with initial and inserted command cases.
   - Fail false: command history only appears in Trace or raw JSON.
   - Proves: Problems 1 and 3.

2. **Selected-command impact chain**
   - Manual path: open an AOL meeting, click a command card, and verify only that command's related nodes are highlighted from command through output.
   - Expected true: unrelated nodes are muted; related decision/action/artifact/minutes nodes remain readable.
   - Fail false: all graph edges render at once, no chain is highlighted, or selection opens only JSON.
   - Proves: Problem 2.

3. **Execution graph edge ingestion**
   - Command: `cd /Users/shock/Projects_local/workspace/mindscape-ai-local-core/web-console && npx vitest run src/components/capabilities/meeting-workbench/AOLMeetingBottomShell.spec.tsx --environment jsdom`
   - Expected true: a neutral `fixture_pack` fixture with `edges` connects command -> run -> output -> artifact; selecting the command marks that path as impact-related.
   - Fail false: edge payload is ignored, or only node existence is asserted.
   - Proves: Problem 2.

4. **Command impact inspector**
   - Manual path: click a command card, open the inspector, and check the default view.
   - Expected true: original command, initial/inserted phase, status, edge count, decision/action/output/artifact counts, and reachable node list appear before raw trace.
   - Fail false: JSON is the first or only command detail view.
   - Proves: Problem 3.

5. **Trackpad and card overflow**
   - Command: `cd /Users/shock/Projects_local/workspace/mindscape-ai-local-core/web-console && npx vitest run src/components/capabilities/meeting-workbench/AOLMeetingBottomShell.spec.tsx --environment jsdom`
   - Expected true: small pixel-mode wheel and horizontal delta do not change zoom; wheel over a command node does not zoom; discrete canvas wheel still zooms.
   - Fail false: trackpad-like wheel changes zoom or node/lane wheel events are prevented.
   - Proves: Problem 4.

6. **Neutral host-shell fixture guard**
   - Command: `cd /Users/shock/Projects_local/workspace/mindscape-ai-local-core && rg -n "performance_direction|character_training|generated_reels_asset|reels_asset|storyboard_proposal" web-console/src/components/capabilities/meeting-workbench/AOLMeetingBottomShell.tsx`
   - Expected true: command exits with no matches in the host-shell implementation.
   - Fail false: local-core host shell synthesizes pack-owned refs or carries pack-specific fallback names.
   - Proves: Problem 5.

7. **Runtime E2E for real meeting data**
   - Command: `.venv/bin/python scripts/e2e/pd_ux_aol_acceptance.py --workspace-id bac7ce63-e768-454d-96f3-3a00e8e1df69`
   - Expected true: S7 remains passed; command event, meeting minutes, action item, memory writeback, and no failed graph nodes are still present.
   - Fail false: command accepted but meeting output does not land, or graph projection loses command/output nodes.
   - Proves: Problems 1, 2, and 3 in the real runtime path.

## 5. Automated test plan

1. Update `web-console/src/components/capabilities/meeting-workbench/AOLMeetingBottomShell.spec.tsx`.
   - Scenario: initial and inserted command events both appear in the Commands lane.
   - Assertions: lane count includes both; card label distinguishes initial vs inserted; each card opens command impact inspector.
   - Prevents regression for Problems 1 and 3.

2. Add selected-command impact test in `AOLMeetingBottomShell.spec.tsx`.
   - Fixtures: execution graph payload with command, run, decision/result, artifact, and non-empty edges.
   - Assertions: selecting the command marks related nodes as highlighted and unrelated nodes as muted; no global edge rendering by default.
   - Prevents regression for Problem 2.

3. Extend the existing canvas zoom test in `AOLMeetingBottomShell.spec.tsx`.
   - Fixtures: wheel events with small pixel delta, horizontal delta, node target, and discrete wheel delta.
   - Assertions: only discrete canvas wheel changes zoom.
   - Prevents regression for Problem 4.

4. Keep `scripts/e2e/pd_ux_aol_acceptance.py` as the runtime guard.
   - Scenario: S7 posts a real meeting command to an attached meeting and requires persisted runtime output.
   - Assertions: `status: passed`, `failed_stages: []`, `session_status: closed`, `minutes_length > 0`, `action_item_count >= 1`, `failed_execution_graph_node_count == 0`.
   - Prevents regression across UI, API, meeting runtime, and graph projection.

## 6. Risks / open questions

1. **Wheel device detection is heuristic**: browsers do not expose a perfect "trackpad vs physical wheel" flag. The guard should stay conservative: if uncertain, prefer scroll over zoom.
2. **Impact edges may be incomplete for older meetings**: older sessions may have nodes but no edges. The implementation needs a trace-order fallback.
3. **Command insertion phase requires a reliable source**: if backend events do not explicitly mark initial vs inserted commands, the UI must derive it from event order until a backend field is added.
4. **Inspector density can grow quickly**: keep command impact as grouped sections and leave raw JSON collapsed by default.
5. **Projection ownership must remain local-core/UI only**: command impact graph is a projection of events, runtime graph, and object graph; it must not become a second canonical owner schema.
