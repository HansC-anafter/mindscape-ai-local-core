# AOL Runtime Workbench Product UX/UI Layout Implementation Plan

Implementation progress on 2026-05-02 and 2026-05-03: the first productization slice has started. The default Meeting Workbench view is now `Work`, the default header no longer leads with raw node/trace counts or raw meeting id, and Work view now renders a selected-subgraph canvas organized as `Focus -> Guidance -> Command -> Runtime -> Outcome -> Next` instead of the fixed seven-lane implementation board. The selected-subgraph canvas now includes a `Provenance path` strip sourced from execution graph edges and caps dense step nodes with hidden-signal summaries. A Work-view `CommandLedgerStrip` lets users select prior commands without opening raw Trace first, and `MeetingWorkbenchStage` now hosts `ObjectOutlinerPanel` as a real left editor column, the inspector rail/panel as a right editor slot, and the command ledger as a dedicated bottom editor band. Work-view inspector labels and initial content now use product task semantics (`Summary`, `Guidance`, `Actions`, `Context`, `Runtime`, `Review`, `Trace`); `Trace` and non-Work modes retain debug/raw inspection. The Guidance inspector now promotes the selected guidance node into a focused decision block with reason, command template, target ref, proposal ref, review routes, and required context while still keeping execution routed through Command Dock. `ObjectOutlinerPanel` now projects role-bearing session context as `Target`, `Sources`, `Evidence`, `Constraints`, `Outputs`, and `Review`, using attach response refs, selected object summary, graph guidance target/proposal refs, staged refs, review routes, and output/artifact graph nodes. Context Bar now derives the current focus role and missing target context from attach response plus graph guidance target metadata; it renders those as Work-view chips without adding button-style execution shortcuts. Command Dock now mirrors missing context as input guidance, has i18n-owned visible/aria copy, and blocks selected-guidance dispatch before writing the Command Ledger when required `@` context is missing. Meeting Workbench now shows AOL session notifications for command accepted/completed/failed states from the same command-ledger/runtime path, without adding a new dispatch surface. Context Bar Next/Missing chips now behave as graph navigation and input-assist controls: they select the relevant node or missing role placeholder, but do not dispatch runtime work. Pack-owned guidance template projection is now the bounded path for command drafts, and the IG/PD product fixture gate verifies IG reference guidance, PD storyboard guidance, required context, Command Ledger submission, and pack workbench context priority without adding IG/PD business branches to local-core.

Critical correction on 2026-05-03: this productization slice is not sufficient to claim the original meeting-led workflow goal. Until `route_meeting_orchestration` and the AOL-to-MeetingEngine bridge are implemented, the Work view can be considered a shell/ledger/projection/materializer product slice only. IG/PD E2E completion must require evidence that `MeetingCommandEnvelope` becomes `HandoffIn` / `RequestContract`, enters `MeetingEngine.run()`, produces ActionIntent / TaskIR, and writes the resulting assets, proposals, review routes, and notifications back to the same meeting graph and Command Ledger.

UX/UI correction on 2026-05-03: AOL runtime graph should inherit the existing Workbench skeleton, but it is not complete until MeetingEngine orchestration state is visible in the same shell. The required correction is not a new generic graph viewer and not more action buttons. The required correction is to add MeetingEngine-led state projection to the existing Context Bar, Object Outliner, Semantic Flow Canvas, Inspector, Command Dock, Command Ledger, Assets lane, and notification loop.

## 0. Original design-goal alignment

The original meeting-session goal is not a generic graph viewer. The product goal is:

1. Use meeting graph nodes to give the user AI-assisted next-step guidance: what object is in focus, what context is missing, what the current command means, what outcome exists, what needs review, and what the user should do next.
2. Use the same meeting graph as the tool-callable workflow spine: user intent, object refs, pack guidance, command templates, runtime execution, artifacts, proposals, review routes, and promotion must be connected by durable node/edge identity.
3. Keep pack-specific thinking inside packs. For example, Performance Direction owns director guidance semantics; local-core owns the generic meeting/session canvas, command ledger, object references, runtime status, and projection surfaces.

This plan therefore changes the visible product framing from `Meeting Graph` to `AOL Runtime Workbench` / `Meeting Workbench`, but it must not remove the graph/node model. The graph remains the runtime and semantic substrate. The Work view should make the graph understandable by projecting it as task-oriented nodes, guidance, commands, outcomes, and review state instead of exposing raw trace lanes as the first screen.

## 0A. Naming pyramid and logic chain

The architecture should use a layered naming pyramid so product copy does not collapse the runtime host framework, the user-facing workbench product, and the meeting-session view into one ambiguous name.

| Layer | Name | Scope | Why |
| --- | --- | --- | --- |
| Architecture/runtime host | `AOL Runtime Shell` | The shared local-core host/container/integration layer that owns selection state, command dock mounting, inspector/canvas/ledger slots, runtime session lifecycle, and pack-owned projection coordination. | Keeps `Shell` in the architecture/code layer, where it means host framework rather than terminal UI or product copy. |
| Product capability | `AOL Runtime Workbench` or external-facing `Runtime Workbench` | The user-facing full-chain AI workbench product powered by the AOL Runtime Shell and callable from any pack workbench. | Emphasizes the runtime, tool-callable, end-to-end work surface instead of implying meeting minutes or agent chat. |
| Single AI collaboration session view | `Meeting Workbench` | A meeting-session-centered view inside AOL Runtime Workbench. | Preserves the existing meeting-session semantics and meeting graph node model. |
| Intent/accounting spine | `Command Ledger` or `Collaboration Ledger` | Durable record of user, agent, pack, and system intent. | Makes every command, tool call, output, proposal, review, and notification traceable. |

Definitions:

- `AOL Runtime Shell` is the shared runtime host framework.
- `AOL Runtime Workbench` is the user-visible full-chain AI workbench product powered by the shell.
- `Meeting Workbench` is one collaboration view inside that shell, centered on a `MeetingSession` and its meeting graph.
- `Command Ledger` is the intentional spine of the Meeting Workbench.

Logic chain:

```text
AOL Runtime Shell
  -> AOL Runtime Workbench
  -> Meeting Workbench
  -> meeting graph nodes
  -> AI next-step guidance
  -> command templates / user intent
  -> MeetingCommandEnvelope
  -> Command Ledger
  -> runtime execution
  -> artifacts / proposals / review routes
  -> AOL Runtime Workbench notification
```

Naming guardrails:

- Do not show `Shell` as the primary user-facing product title; in UI copy, use `AOL Runtime Workbench`, `Runtime Workbench`, or the active view name.
- Do not describe the whole product capability as only `Meeting Workbench`; that can read like meeting minutes, agent discussion, or a conversation UI.
- Do not describe the meeting-session view as only `Graph`; that can read like a passive proof viewer.
- Do not describe the ledger as only command history; it is the collaboration record that joins intent, execution, assets, and review.

## 0B. Element alignment requirements

Every visible Work-view element must serve at least one of the two original goals: AI next-step guidance or AI-guided tool-callable workflow. If an element cannot be tied to a graph node, graph edge, command envelope, guidance state, runtime event, artifact/proposal, review route, or recovery state, it is not part of the P0 product layout.

| Element | Required concept alignment | Product rule | Deviation to avoid |
| --- | --- | --- | --- |
| Workbench/view title | Names the runtime workbench and active meeting collaboration center. | Use `AOL Runtime Workbench` or `Runtime Workbench` for product framing; use `Meeting Workbench` for the active meeting-session view; keep `Meeting Graph` for Debug/Trace metadata only. | Do not title the product surface as `Shell`, an object-only workspace, or a raw graph viewer. |
| Context Bar | Orients the user in the current meeting graph state. | Show focus object, role, status, runtime, next-step chip, and missing-context chip. | Do not show node count, trace count, or raw ids in Work view. |
| Object Outliner | Shows role-bearing meeting context that guidance and commands can use. | Group objects by Target, Sources, Evidence, Constraints, Outputs, and Review; show missing required roles as placeholders. | Do not become a file tree or a generic object browser. |
| Semantic Flow Canvas | Main graph-node surface for cognition and workflow. | Render selected subgraph with Object, Guidance, Command, Run, Outcome, Artifact, Proposal, Review, Next, and Blocked nodes. | Do not render fixed implementation lanes as the Work view. |
| Inspector | Explains the selected node and exposes decision/task controls. | Default tabs must answer Summary, Guidance, Actions, Relations, and Runtime for the selected graph node. | Do not make raw trace, JSON, prompts, or patch internals the default experience. |
| Command Dock | Converts guidance/user intent into a callable workflow. | Templates and mentions become a `MeetingCommandEnvelope`; submit is the execution entrypoint. | Do not let random card buttons bypass the command ledger. |
| Command Ledger | Durable intentional spine of the meeting graph. | Accepted/running/completed command rows must be backend-ledger rows with `command_id`. | Do not infer product command history only from trace events. |
| Notifications | Closes the loop from graph state to user action. | Notify on accepted, running, completed, failed, needs-review, asset-landed, degraded-proof, and runtime-unavailable states. | Do not show disconnected UI-only toasts. |
| Trace/Debug | Audit and recovery for advanced users. | Keep raw replay, node counts, JSON, and legacy lane board behind Trace/Debug. | Do not let debug categories lead the Work view. |

## 0C. Shell invocation contract

`AOL Runtime Shell` is the local-core, site-wide host/integration layer that opens from pack workbenches as a bottom/overlay work surface. `AOL Runtime Workbench` is the user-facing product surface powered by that shell. `Meeting Workbench` is the meeting-session-centered collaboration view inside the product surface. None of these layers is an IG-specific or PD-specific page.

Pack workbenches may call the shell through generic AOL operations only:

1. open/focus shell with an `ObjectRef`
2. attach object to the meeting with a role
3. insert an `@owner.kind:id` mention
4. insert a command template
5. request pack-owned guidance projection
6. open owner surface for pack-native detail

Local-core owns the AOL Runtime Shell, AOL Runtime Workbench product surface, Meeting Workbench view, meeting session, command ledger, graph projection, runtime status, review surface, and notifications. Packs own object schemas, relation semantics, guidance semantics, materializers, and owner detail pages. Therefore IG and PD can both launch the same shell, but the shell must render pack-specific meaning only through bounded projections, guidance nodes, command templates, object refs, and materialized outputs.

## 0D. UX/UI inheritance and MeetingEngine orchestration completion gates

The current implementation can be inherited as the product shell skeleton. It cannot be treated as complete UX until the user can see the meeting-led orchestration chain and its proof.

### 0D.1 Inherit without redesign

| Existing UI element | Current implementation evidence | Decision |
| --- | --- | --- |
| Four-editor workbench skeleton | `MeetingWorkbenchStage.tsx` renders Object Outliner, Semantic Flow Canvas, Inspector slot, and bottom Command Ledger band. | Keep as the P0 layout shell. |
| Work-view lane vocabulary | `WORK_GRAPH_LANES` defines `Focus`, `Guidance`, `Command Ledger`, `Runtime`, `Outcomes`, `Assets`, and `Next`. | Keep as product vocabulary. |
| Runtime data readers | `useMeetingThreadData.ts` reads execution graph, meeting events, artifacts, and refreshes on command-ledger events. | Reuse for orchestration proof and asset proof. |
| Guidance/template interaction rule | Current Guidance and command template projection already inserts command drafts and avoids hidden card dispatch. | Keep. Execution still enters through Command Dock. |

### 0D.2 Required UX/UI completion

| Surface | Required P0 addition | Unique implementation path | Acceptance evidence |
| --- | --- | --- | --- |
| Command Dock | Submit AOL object/guidance commands through MeetingEngine orchestration by default. | `meetingCommandLedger.ts:submitMeetingCommandEnvelope()` writes `metadata.dispatch_mode = "route_meeting_orchestration"` for object refs, guidance, selected pack tool, or context objects. | Submitted payload for cross-pack object workflow and pack-object guidance discussion fixtures never contains `route_playbook` or `route_object_action` from web-console. |
| Command local task state | Interpret orchestration response, not direct route-owned response. | `meetingCommandSubmit.ts:createMeetingCommandSubmitHandler()` reads `dispatch_result.meeting_orchestration.task_ir_id`, `status`, `dispatch_status`, `asset_ids`, `proposal_ids`, `review_routes`. | Optimistic task becomes `running`, `ready`, `needs_review`, or `error` based on orchestration result, with `task_ir_id` in node output. |
| Semantic Flow Canvas | Render the meeting-led workflow chain. | `meetingGraphProjection.ts:projectMeetingGraph()` or the successor projection module maps command/orchestration metadata into nodes. | Work canvas shows a selectable path: `Intent -> Context Attachments -> RequestContract -> ActionIntent -> TaskIR -> Dispatch -> Artifact/Proposal -> Review/Next`. |
| Inspector Runtime tab | Show proof that command entered MeetingEngine. | `PropertiesInspector.tsx` / `MeetingDefaultInspectorContent.tsx` reads selected node metadata. | Runtime tab shows `dispatch_mode`, `meeting_id`, `command_id`, `task_ir_id`, `MeetingEngine.run()` status, and dispatch status. |
| Inspector Guidance tab | Show pack guidance as hints consumed by MeetingEngine, not hard UI routes. | Guidance content reads selected guidance node metadata and command template data. | Guidance tab distinguishes `candidate_playbook_hint` from explicit direct playbook override. |
| Assets lane | Show asset database and file proof. | `useMeetingThreadData.ts:fetchMeetingArtifacts()` reads `/api/v1/workspaces/{workspace_id}/artifacts?thread_id={meeting_id}`; artifact nodes include storage/file metadata. | Artifact node displays DB artifact id plus `storage_ref` or resolved `file_path`; missing file proof renders `Blocked` or degraded proof node. |
| Notifications | Close the loop from orchestration to session. | `meetingCommandSubmit.ts:createMeetingCommandSubmitHandler()` dispatches session notifications from `meeting_orchestration` response and later refresh events. | Notifications use the same `meeting_id`, `command_id`, and `task_ir_id` where available; states include accepted, planning, dispatched, asset landed, needs review, completed, failed. |

### 0D.3 Non-goals

- Do not redesign the whole AOL runtime graph UI before P0 bridge implementation.
- Do not add action buttons across cards to compensate for missing orchestration.
- Do not encode IG/PD-specific workflow branches inside local-core UI.
- Do not claim IG/PD E2E from fixture tests, direct dispatch, or local optimistic nodes.
- Do not show raw trace, node count, or JSON as the first Work-view proof.

## 1. Problem list

1. **The current pane title and first screen communicate an internal graph tool, not a product workbench**: the host pane is labeled `Meeting Graph`, while the visible shell starts with object/session toggles, graph mode tabs, node counts, trace counts, and a fixed graph board. Evidence: E1, E2. Severity: 5. Detection: 3. Priority: 15.
2. **The current layout exposes implementation categories instead of the user's work state**: the center canvas renders seven fixed lanes (`Context`, `Object Graph`, `Commands`, `Runs`, `Outputs`, `Artifacts`, `Next`) and each lane owns independent card stacks, so users must infer the actual workflow from low-level categories. Evidence: E3, E4. Severity: 5. Detection: 4. Priority: 20.
3. **The command experience is present but visually subordinate to the debug graph**: the command bar supports mentions and pack tools, but it sits below a board that does not make command grammar, object roles, or next operations the primary interaction model. Evidence: E5, E6. Severity: 5. Detection: 3. Priority: 15.
4. **Inspector content is organized by system tabs, not by decision-making tasks**: the inspector offers `Object`, `Runtime`, `Session`, `Trace`, `Graph`, `Prompts`, and `Patch`; command impact exists inside Trace and raw replay events plus JSON remain prominent. Evidence: E7, E8. Severity: 4. Detection: 3. Priority: 12.
5. **There is no productized empty/loading/error model for the workbench journey**: current empty states include `No nodes`, `No graph projection available`, `No events for this filter`, and `No review routes staged`, but they do not guide a user toward selecting an object, inserting an `@` reference, submitting a command, or reviewing an outcome. Evidence: E4, E8. Severity: 4. Detection: 3. Priority: 12.
6. **The prior architecture plans define synchronized editors and command envelopes, but not a frontend layout contract**: the new canvas and command-envelope plans specify projection and ledger concepts, but they do not define a product-ready composition, dimensions, primary states, copy hierarchy, or responsive behavior. Evidence: E9, E10. Severity: 4. Detection: 4. Priority: 16.
7. **The UX cannot be considered complete until command identity is backend-owned**: a polished layout can improve comprehension, but the meeting cannot act as the collaboration center while command rows are inferred from events/tasks instead of accepted through a command API and ledger. Evidence: E10, E11. Severity: 5. Detection: 5. Priority: 25.
8. **The frontend implementation needs component boundaries before productization**: the current shell is already a large aggregation point for projection, editor, inspector, command bar, and dispatch behavior, so the layout work must define module boundaries instead of adding more UI into the same component. Evidence: E12. Severity: 4. Detection: 4. Priority: 16.

## 2. Evidence

E1. `AddressableObjectMeetingPane` renders the visible product title as `Meeting Graph` and exposes compact/default/expanded pane controls. Source: `web-console/src/components/capabilities/AddressableObjectHostShell.tsx:L547-L607`.

E2. `MeetingHeaderToolbar` renders `Object`, `Sessions`, `flow/runs/trace`, node count, trace count, and active meeting id in the first toolbar. Source: `web-console/src/components/capabilities/meeting-workbench/AOLMeetingBottomShell.tsx:L1900-L1972`.

E3. `MeetingTaskCanvas` groups nodes by `GRAPH_LANES`, pans/zooms the canvas, and renders the lanes as `grid-cols-[repeat(7,minmax(11rem,15rem))]`. Source: `web-console/src/components/capabilities/meeting-workbench/AOLMeetingBottomShell.tsx:L1976-L2248`.

E4. The fixed lane card UI renders per-lane counts, node cards, impact badges, and `No nodes` empty states, but it does not produce an outliner/canvas/inspector/ledger editor model. Source: `web-console/src/components/capabilities/meeting-workbench/AOLMeetingBottomShell.tsx:L2148-L2244`.

E5. `MeetingCommandBar` already supports command text, submit, pack tool selection, active meeting gating, mention options, and mention application. Source: `web-console/src/components/capabilities/meeting-workbench/AOLMeetingBottomShell.tsx:L2251-L2305`.

E6. The command envelope plan defines command grammar as the main UX and says UI surfaces should insert references/templates rather than execute hidden actions. Source: `docs-internal/implementation/aol-runtime-workbench-2026-05-02/meeting-command-envelope-collaboration-ledger-implementation-plan-2026-05-02.md:L131-L142`.

E7. `MeetingInspectorPanel` defines system tabs through `InspectorTab` and renders object, runtime, session, trace, graph, prompts, and patch views. Source: `web-console/src/components/capabilities/meeting-workbench/AOLMeetingBottomShell.tsx:L224-L235`, `web-console/src/components/capabilities/meeting-workbench/AOLMeetingBottomShell.tsx:L2480-L2915`.

E8. Trace view shows `Command impact`, then `Raw replay events`, filter buttons, event list, and JSON; graph view shows `Bounded object graph` and raw relation badges. Source: `web-console/src/components/capabilities/meeting-workbench/AOLMeetingBottomShell.tsx:L2680-L2865`.

E9. The canvas implementation plan proposes `ObjectOutliner`, `SemanticFlowCanvas`, `PropertiesInspector`, and `CommandLedger`, but it does not define visual layout dimensions or product states. Source: `docs-internal/implementation/aol-runtime-workbench-2026-05-02/aol-runtime-workbench-canvas-implementation-plan-2026-05-02.md:L88-L107`.

E10. The command envelope plan proposes `MeetingCommandEnvelope`, `/meetings/{meeting_id}/commands`, `MeetingCommandStore`, and command-ledger projection, but it does not define the frontend layout where the command grammar becomes primary. Source: `docs-internal/implementation/aol-runtime-workbench-2026-05-02/meeting-command-envelope-collaboration-ledger-implementation-plan-2026-05-02.md:L46-L150`.

E11. The command envelope plan now requires server-side command grammar normalization, a backend-generated `command_id`, `GET/POST /api/v1/workspaces/{workspace_id}/meetings/{meeting_id}/commands`, and graph projection from ledger rows before full product acceptance. Source: `docs-internal/implementation/aol-runtime-workbench-2026-05-02/meeting-command-envelope-collaboration-ledger-implementation-plan-2026-05-02.md:L70-L150`.

E12. `AOLMeetingBottomShell.tsx` is 4181 lines as of 2026-05-02 (`wc -l /Users/shock/Projects_local/workspace/mindscape-ai-local-core/web-console/src/components/capabilities/meeting-workbench/AOLMeetingBottomShell.tsx`), which confirms the product layout work needs extraction boundaries.

E13. IG declares `reference` as an addressable object that supports summary, detail, actions, meeting projection, and graph projection. Source: `/Users/shock/Projects_local/workspace/mindscape-ai-cloud/capabilities/ig/manifest.yaml:L429-L468`.

E14. Performance Direction declares meeting projections/materializers for `storyboard_scene` and `storyboard_proposal_artifact`, graph projections for storyboard/proposal/generated assets, and `pd_director_guidance` / `pd_director_guidance_compile` for director guidance. Source: `/Users/shock/Projects_local/workspace/mindscape-ai-cloud/capabilities/performance_direction/manifest.yaml:L246-L303`, `/Users/shock/Projects_local/workspace/mindscape-ai-cloud/capabilities/performance_direction/manifest.yaml:L435-L452`, `/Users/shock/Projects_local/workspace/mindscape-ai-cloud/capabilities/performance_direction/manifest.yaml:L1218-L1248`.

## 3. Proposed changes

### Change 1: Define the product surface as `AOL Runtime Workbench`, with `Meeting Workbench` as the default session view

Resolves Problems 1 and 6.

- Use `AOL Runtime Workbench` or `Runtime Workbench` as the product framing.
- Rename the visible meeting-session pane title from `Meeting Graph` to `Meeting Workbench`.
- Keep `Meeting Graph` as a debug/runtime concept available in advanced views.
- First-screen promise: "the selected object, current command, produced outcome, and next operation are visible without opening raw trace."
- Do not use explanatory marketing copy in-app. Use concise product labels:
  - `Meeting Workbench`
  - `Focus`
  - `Session Objects`
  - `Command`
  - `Outcome`
  - `Review`
  - `Trace`

### Change 2: Replace the fixed lane board with a four-editor workbench layout

Resolves Problems 2, 4, and 6.

Primary expanded/default layout:

```text
┌──────────────────────────────────────────────────────────────────────────────┐
│ Context Bar: Focus | Role | Status | Runtime | Next step | Missing context │
├───────────────┬──────────────────────────────────────────────┬───────────────┤
│ Object        │ Semantic Flow Canvas                         │ Inspector     │
│ Outliner      │                                              │               │
│ 260px         │ selected object/command impact graph          │ 360px         │
│               │                                              │               │
├───────────────┴──────────────────────────────────────────────┴───────────────┤
│ Command Dock: prompt with @ chips | command templates | command ledger       │
└──────────────────────────────────────────────────────────────────────────────┘
```

- Use CSS grid in the shell body:
  - rows: `44px minmax(0,1fr) 132px`
  - columns: `260px minmax(520px,1fr) 360px`
- Compact pane behavior:
  - hide Inspector behind right rail tabs
  - collapse Object Outliner into a drawer
  - keep Command Dock visible
- Expanded pane behavior:
  - show all four editors
  - center canvas gets the largest width
  - allow inspector width to resize between `320px` and `460px`
- Module boundary:
  - `AOLRuntimeWorkbench.tsx` owns the four-editor layout and shared selection state
  - `ObjectOutliner.tsx` owns session object groups
  - `SemanticFlowCanvas.tsx` owns selected subgraph rendering
  - `PropertiesInspector.tsx` owns task-oriented detail panels
  - `CommandDock.tsx` owns command input, templates, and submit state
  - `CommandLedger.tsx` owns command history and command selection
  - `AOLMeetingBottomShell.tsx` remains a compatibility wrapper/data loader during migration

### Change 3: Define the Context Bar as the meeting-graph orientation layer

Resolves Problems 1, 2, and 5.

Context Bar content:

- left: `Meeting Workbench`
- focus chip: object title, owner pack, object kind, role
- status chips:
  - `Drafting`
  - `Running`
  - `Completed`
  - `Needs review`
  - `Blocked`
- runtime chip:
  - executor id or `No runtime`
- next-step chip:
  - current `Next` or `Blocked` node title from the selected meeting graph projection
- missing-context chip:
  - required role or reference that prevents the next command from being valid, for example `Missing target`
- controls:
  - `Work`
  - `Trace`
  - `Debug`
  - compact/default/expanded pane icons

Rules:

- Do not show raw node count or trace count in the default Work view.
- Move node count and trace count to Debug view.
- If no object is attached, the focus chip should say `No focus object` and the command dock should still allow `@` search.
- The next-step chip must be derived from graph/guidance state, not handwritten frontend copy.

### Change 4: Define Object Outliner as the session object map

Resolves Problems 2 and 5.

Object Outliner sections:

- `Target`
- `Sources`
- `Evidence`
- `Constraints`
- `Outputs`
- `Review`

Each row:

- icon by generic kind (`object`, `artifact`, `proposal`, `review`)
- title
- owner pack/object kind subtitle
- role badge
- status dot
- no action button matrix

Interactions:

- click selects object and updates center canvas plus inspector
- drag/drop is not P0
- row secondary action menu is limited to `Insert mention`, `Open owner`, `Remove from session`

Empty state:

- `Select an object from the workbench or type @ to reference one.`
- Missing role placeholders:
  - if guidance requires a role that is not attached, render a placeholder row such as `Missing target`
  - placeholder rows may insert a mention/search affordance, but must not dispatch work

### Change 5: Define Semantic Flow Canvas as selected subgraph, not full trace board

Resolves Problems 2, 4, and 5.

Canvas default scopes:

- selected object: `object -> guidance -> command(s)/next -> output/proposal/review`
- selected command: `command -> run -> outcome -> provenance -> next`
- selected guidance: `guidance -> required context -> command template -> next`
- no selection: meeting summary with focus object, latest command, and recommended next step

Node taxonomy:

- `Object`
- `Guidance`
- `Command`
- `Run`
- `Outcome`
- `Artifact`
- `Proposal`
- `Review`
- `Next`
- `Blocked`

Edge labels:

- `uses`
- `targets`
- `runs`
- `produces`
- `stages`
- `reviews`
- `promotes`
- `derived from`
- `suggests`
- `requires`
- `blocked by`

Visual rules:

- show at most one selected subgraph by default
- use muted background for unrelated nodes only when user explicitly enables context expansion
- degraded proof nodes must be visible with a blocked/warning state and clear reason
- guidance nodes must be visible in Work view when pack guidance exists; they cannot live only inside Inspector
- no raw JSON in canvas nodes
- lane board can remain under Debug view only

### Change 6: Define Inspector as product task panels

Resolves Problems 4 and 5.

Default inspector tabs in Work view:

- `Summary`
- `Guidance`
- `Actions`
- `Relations`
- `Runtime`

Advanced tabs:

- `Trace`
- `Raw`

Summary:

- object/command title
- role
- status
- short description
- related outputs/review routes

Guidance:

- pack-owned guidance cards
- selected `Guidance` graph node details
- missing context
- command templates
- required role/object list
- no auto-dispatch

Actions:

- generic verbs and templates, not per-card button sprawl
- `Insert command template`
- `Open owner surface`

Relations:

- bounded object relations from `/object-graph/project`
- relation kind, target title, direction

Runtime:

- executor/runtime status
- command status
- task/execution ids

Trace/Raw:

- raw replay events
- JSON
- hidden behind advanced tabs by default

### Change 7: Define Command Dock as the primary collaboration entry

Resolves Problems 3 and 6.

Command Dock layout:

```text
┌──────────────────────────────────────────────────────────────┐
│ [@ chips + command input............................] [Send] │
│ Suggestions: /stage /review /promote | missing target        │
│ Ledger: #1 completed | #2 running | #3 draft                 │
└──────────────────────────────────────────────────────────────┘
```

Rules:

- command input is always visible in default and expanded modes
- command grammar uses mention chips and typed text
- UI surfaces insert mentions or templates into this dock
- no hidden dispatch from random card buttons
- ledger entries are clickable and drive canvas selection
- inserted templates should carry source guidance/template identity so the resulting command can be traced back to the graph node that suggested it
- pack tool dropdown should become secondary; default route is `Auto route`
- submit calls the backend command API once available; direct `sendMessage(action_params)` remains only as a temporary legacy fallback behind an explicit compatibility path
- draft rows may be optimistic in the UI, but accepted/running/completed rows must come from backend command ledger state

Command states:

- `Draft`
- `Accepted`
- `Running`
- `Completed`
- `Failed`
- `Needs review`
- `Superseded`

### Change 8: Define productized state model

Resolves Problem 5.

Required states:

- no active meeting:
  - context bar: `No active session`
  - command dock disabled except `Start session`
- no focus object:
  - outliner empty state
  - canvas shows `Reference an object with @ or select one from the workbench`
- focus object attached:
  - canvas shows object summary, guidance nodes, missing context, and available command templates
- command draft:
  - command appears in ledger as draft
- command running:
  - canvas highlights command -> run
  - inspector runtime tab shows executor
- command completed:
  - canvas shows outcome and provenance
  - command dock suggests follow-up templates derived from pack guidance or graph state
- needs review:
  - review route appears in inspector and canvas
- degraded evidence:
  - blocked node appears with reason and recovery action
- runtime unavailable:
  - context bar runtime chip shows blocked state
  - command dock can draft but send is blocked with reason

### Change 9: Define implementation sequence and product-readiness gates

Resolves Problems 6, 7, and 8.

Sequence:

1. Extract projection and layout modules while preserving current data loading.
2. Add legacy-inferred command entries only as degraded compatibility state.
3. Wire Command Dock to the backend command API from the command-envelope plan.
4. Switch Work view to backend command-ledger rows as authoritative.
5. Move fixed lane board to Debug view.
6. Run visual, keyboard, and runtime smoke checks before calling the UI product-ready.

Product-readiness gates:

- default title is `Meeting Workbench`
- every Work-view UI element maps to graph state, guidance state, command envelope state, runtime state, artifact/proposal state, review state, or recovery state
- context bar next-step and missing-context chips are derived from graph/guidance state
- guidance appears as selectable canvas nodes when pack guidance exists
- command dock is always visible in default/expanded modes
- accepted command rows come from backend ledger, not only event inference
- selected object and selected command both produce readable subgraphs
- raw trace and JSON are hidden under advanced tabs
- no pack-specific semantics are hard-coded in local-core workbench components

## 4. Verification SOP

1. **Default product title and orientation**
   - Command: `cd /Users/shock/Projects_local/workspace/mindscape-ai-local-core/web-console && npx vitest run src/components/capabilities/meeting-workbench/AOLRuntimeWorkbenchLayout.spec.tsx --environment jsdom`
   - Expected true: default title is `Meeting Workbench`; node count and trace count are absent from Work view and present only in Debug view.
   - Fail false: the first-screen title remains `Meeting Graph` or Work view leads with trace/node counts.
   - Proves: Problems 1 and 2.

2. **Four-editor layout renders in expanded/default mode**
   - Command: `cd /Users/shock/Projects_local/workspace/mindscape-ai-local-core/web-console && npx vitest run src/components/capabilities/meeting-workbench/AOLRuntimeWorkbenchLayout.spec.tsx --environment jsdom`
   - Expected true: `ObjectOutliner`, `SemanticFlowCanvas`, `PropertiesInspector`, and `CommandDock` are present and share selection state.
   - Fail false: center board is still the only meaningful surface or selection does not synchronize.
   - Proves: Problems 2, 4, and 6.

3. **Command Dock remains primary**
   - Manual path: open an installed pack object surface, select an object, insert mention/template, submit from Command Dock.
   - Expected true: card interaction inserts an `@owner.kind:id` chip/template; no run starts until the dock command is submitted.
   - Fail false: random card actions directly start runs or the command dock is hidden in default layout.
   - Proves: Problem 3.

4. **Inspector defaults to product tasks**
   - Manual path: click object, command, artifact, and review route nodes.
   - Expected true: inspector opens `Summary`, `Guidance`, `Actions`, or `Relations` by default; raw JSON is under advanced `Raw`.
   - Fail false: Trace/Raw is the first or only meaningful detail view.
   - Proves: Problem 4.

5. **Guidance is graph state, not only side-panel text**
   - Manual path: attach an installed pack object that has pack-owned guidance.
   - Expected true: a selectable `Guidance`, `Next`, or `Blocked` node appears in Work view; clicking it opens Guidance with reason, required roles, and command templates.
   - Fail false: guidance exists only as inspector text or a detached card with no graph node.
   - Proves: original design-goal alignment.

6. **State model coverage**
   - Command: `cd /Users/shock/Projects_local/workspace/mindscape-ai-local-core/web-console && npx vitest run src/components/capabilities/meeting-workbench/AOLRuntimeWorkbenchStates.spec.tsx --environment jsdom`
   - Expected true: no meeting, no focus object, running command, completed command, needs review, degraded evidence, and runtime unavailable states render distinct user-facing states.
   - Fail false: states collapse into `No nodes`, raw errors, or silent empty panels.
   - Proves: Problem 5.

7. **Responsive behavior**
   - Manual path or Playwright: test compact/default/expanded pane sizes.
   - Expected true: compact keeps Command Dock visible and moves outliner/inspector to drawers; expanded shows all four editors.
   - Fail false: command entry disappears, text overlaps, or inspector consumes the canvas.
   - Proves: Problems 1, 2, and 6.

8. **Command Dock uses backend command ledger in full mode**
   - Manual path: submit a pack-owned template containing `@owner.kind:id` source and target refs from the Command Dock and inspect network plus ledger row.
   - Expected true: submit calls `/api/v1/workspaces/{workspace_id}/meetings/{meeting_id}/commands`; accepted ledger row returns `command_id`; runtime dispatch is linked to that id.
   - Fail false: UI only calls direct `sendMessage(action_params)` or the ledger row is inferred after the fact.
   - Proves: Problems 3 and 7.

9. **Component boundary check**
   - Command: `cd /Users/shock/Projects_local/workspace/mindscape-ai-local-core && rg --files web-console/src/components/capabilities/meeting-workbench | rg "AOLRuntimeWorkbench|ObjectOutliner|SemanticFlowCanvas|PropertiesInspector|CommandDock|CommandLedger"`
   - Expected true: product workbench modules exist outside the legacy bottom shell.
   - Fail false: layout is implemented by expanding only `AOLMeetingBottomShell.tsx`.
   - Proves: Problem 8.

## 5. Automated test plan

1. Add `web-console/src/components/capabilities/meeting-workbench/AOLRuntimeWorkbenchLayout.spec.tsx`.
   - Scenario: render product layout with focus object, command, run, artifact, and review route.
   - Assertions: title, context bar, outliner, semantic canvas, inspector, command dock, and advanced debug mode are correctly present.
   - Prevents regressions for Problems 1, 2, 4, and 6.

2. Add `web-console/src/components/capabilities/meeting-workbench/AOLRuntimeWorkbenchStates.spec.tsx`.
   - Scenario: render no meeting, no focus object, running, completed, review, degraded, and runtime unavailable fixtures.
   - Assertions: each state has distinct copy, disabled/enabled command behavior, and visible recovery/next step.
   - Prevents regressions for Problem 5.

3. Extend command-bar mention tests.
   - Target: current `AOLMeetingBottomShell.spec.tsx` during migration, later `AOLCommandDock.spec.tsx`.
   - Scenario: surface inserts mention/template; command dock submits envelope.
   - Assertions: no hidden dispatch before submit; ledger receives draft/accepted/running/completed updates.
   - Prevents regressions for Problem 3.

4. Add visual regression screenshots with Playwright.
   - Target sizes:
     - compact pane
     - default pane
     - expanded pane
     - desktop full viewport
     - narrow desktop width
   - Assertions: no text overlap, command dock visible, inspector not covering canvas, selected subgraph readable.
   - Prevents regressions for Problems 1, 2, and 6.

5. Keep existing `AOLMeetingBottomShell.spec.tsx` as compatibility coverage.
   - Scenario: old host pane entry still mounts the new product layout and can open Debug lane board.
   - Assertions: session loading, object context, command dispatch, and inspector rails remain reachable.
   - Prevents regressions while replacing the fixed lane board.

6. Add `web-console/src/components/capabilities/meeting-workbench/CommandDock.spec.tsx`.
   - Scenario: optimistic draft, backend accepted row, running row, completed row, failed row, and legacy fallback.
   - Assertions: backend rows are authoritative; legacy inferred rows are visually degraded; no hidden dispatch happens before explicit submit.
   - Prevents regressions for Problems 3 and 7.

7. Add a component-boundary test or CI grep.
   - Scenario: projection merge and command submit are not reintroduced into presentational editor components.
   - Assertions: `AOLRuntimeWorkbench` receives a projection and callbacks; editor components do not call pack execution APIs directly.
   - Prevents regressions for Problem 8.

## 6. Risks / open questions

1. **Bottom-pane height may be too constrained for a full editor layout**: compact/default modes must prioritize Command Dock and selected subgraph; expanded mode should be the recommended product experience.
2. **Outliner width and inspector width may need user resizing**: P0 can use fixed widths, but heavy sessions will benefit from resizable split panes.
3. **Pack guidance may arrive after layout work**: Inspector must support a loading/missing guidance state without falling back to raw trace.
4. **The word "session" may compete with existing meeting/session terms**: UI copy should use `AOL Runtime Workbench` for the product surface, `Meeting Workbench` for the active meeting-session view, and reserve `Meeting ID` for advanced/debug metadata.
5. **Visual density can regress into debug UI**: default Work view must cap visible data, hide raw JSON, and show selected subgraphs only.
6. **Accessibility must be preserved**: outliner rows, canvas nodes, inspector tabs, and command dock mentions need keyboard navigation and ARIA labels before the layout is considered product-ready.
7. **Backend command ledger is a hard dependency for final UX**: without it, the layout can be a preview, but it cannot honestly claim that the meeting is the central collaboration platform.
8. **Direct-dispatch compatibility can leak into product mode**: temporary `sendMessage(action_params)` fallback must be isolated and removed or hidden behind Debug/legacy mode once `/commands` is live.
