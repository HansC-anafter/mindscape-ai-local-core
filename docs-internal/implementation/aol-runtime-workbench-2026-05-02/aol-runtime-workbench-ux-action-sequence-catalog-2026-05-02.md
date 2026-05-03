# AOL Runtime Workbench UX/UI Action Sequence Catalog

Date: 2026-05-02

Status: Productized UX/UI action catalog for the AOL Runtime Shell, the AOL Runtime Workbench product surface, and its Meeting Workbench view.

Owner surface: local-core AOL runtime workbench, with pack-owned semantics supplied by installed capability packs.

## Purpose

This document enumerates the operable UX/UI actions for the AOL Runtime Shell, the AOL Runtime Workbench product surface, and its Meeting Workbench view. Each action is modeled through the same execution chain:

```text
user intent -> UX/UI operation -> AOL session feedback -> meeting execution -> asset landing -> AOL session notification
```

The goal is to make every visible operation productized, command-ledger-backed, and inspectable from the AOL session canvas. This is not a proposal for adding action buttons everywhere. The canonical operation is still the submitted `MeetingCommandEnvelope`; UI surfaces should primarily select objects, insert mentions, insert templates, open owner detail, or expose review/provenance.

## Shell Scope

`AOL Runtime Shell` is the local-core site-wide host/integration layer opened from the bottom/overlay work surface. IG Workbench, PD Workbench, and later pack workbenches can call the shell, but they do not own it. `AOL Runtime Workbench` is the user-facing workbench product powered by the shell. `Meeting Workbench` is the meeting-session-centered collaboration view inside that product surface.

Pack workbenches may invoke the shell by opening it with an object, attaching a role-bearing object, inserting a mention, inserting a command template, requesting pack-owned guidance, or opening the pack-native owner detail. The shell owns meeting session state, Meeting Workbench view state, command ledger, canvas projection, runtime status, review route rendering, and notifications.

## Naming Pyramid And Logic Chain

| Layer | Name | UX meaning |
| --- | --- | --- |
| Architecture/runtime host | `AOL Runtime Shell` | Shared local-core host framework for selection state, runtime session lifecycle, mounted editors, command dock, inspector, canvas, ledger, and pack-owned projections. |
| Product capability | `AOL Runtime Workbench` / `Runtime Workbench` | User-facing full-chain workbench for AI-guided runtime work across packs. |
| Collaboration session view | `Meeting Workbench` | Meeting-session-centered view that renders meeting graph nodes, guidance, commands, runtime, assets, and review. |
| Intent spine | `Command Ledger` / `Collaboration Ledger` | Durable ledger that joins user intent, AI guidance, command envelopes, execution, outputs, and review. |

```text
AOL Runtime Shell
  -> AOL Runtime Workbench
  -> Meeting Workbench view
  -> meeting graph guidance nodes
  -> command templates / user command
  -> MeetingCommandEnvelope
  -> Command Ledger
  -> runtime execution
  -> artifact/proposal/review landing
  -> session notification
```

## Original Design Goal Alignment

The meeting session is intended to be the central AI-assisted collaboration platform, not a passive log viewer. The action catalog is aligned to two original goals:

1. AI-guided next-step cognition: graph nodes must tell the user what is selected, what context is missing, what can be done next, what is running, what was produced, and what needs review.
2. AI-guided tool-callable workflow: the same node chain must route user intent through object refs, pack guidance, command templates, runtime execution, asset/proposal landing, review, and promotion.

For that reason, `AOL Runtime Shell` is the architecture/code-layer name, `AOL Runtime Workbench` is the product capability name, and `Meeting Workbench` is the product-facing name of the meeting-session view. None of these replaces the meeting graph. The graph/node model remains the semantic runtime substrate, while Work view renders it as readable task nodes instead of raw trace/debug lanes.

## Evidence Baseline

- The productized shell/view naming pyramid defines `AOL Runtime Shell` as the architecture host, `AOL Runtime Workbench` as the user-facing product surface, and `Meeting Workbench` as the meeting-session view, with `Meeting Graph` retained as an advanced/debug concept. Evidence: `aol-runtime-workbench-product-ux-ui-layout-implementation-plan-2026-05-02.md:L13-L79`, `aol-runtime-workbench-product-ux-ui-layout-implementation-plan-2026-05-02.md:L124-L138`.
- The target layout is a four-editor workbench: Context Bar, Object Outliner, Semantic Flow Canvas, Inspector, and Command Dock/Ledger. Evidence: `aol-runtime-workbench-product-ux-ui-layout-implementation-plan-2026-05-02.md:L140-L177`.
- Context Bar, Object Outliner, Canvas, Inspector, Command Dock, and product states are specified in the UX/UI plan. Evidence: `aol-runtime-workbench-product-ux-ui-layout-implementation-plan-2026-05-02.md:L179-L415`.
- The command contract is `MeetingCommandEnvelope`, including `origin_surface`, actor, intent text, context objects, requested action, expected outputs, write mode, thread id, and metadata. Evidence: `meeting-command-envelope-collaboration-ledger-implementation-plan-2026-05-02.md:L54-L74`.
- The target backend command route is `POST /api/v1/workspaces/{workspace_id}/meetings/{meeting_id}/commands`, paired with a read route for the command ledger. Evidence: `meeting-command-envelope-collaboration-ledger-implementation-plan-2026-05-02.md:L76-L90`.
- The command ledger is the stable intentional spine and should be projected into the canvas. Evidence: `meeting-command-envelope-collaboration-ledger-implementation-plan-2026-05-02.md:L92-L159`.
- UI surfaces should insert references/templates into the command dock and avoid broad button matrices. Evidence: `meeting-command-envelope-collaboration-ledger-implementation-plan-2026-05-02.md:L132-L143`.
- IG reference guidance should produce command templates, not hidden auto-dispatch actions. Evidence: `IG_REFERENCE_AOL_GRAPH_AND_GUIDANCE_IMPLEMENTATION_PLAN_2026-05-02.md:L89-L146`.
- IG relation targets must either be first-class exported objects or bounded display targets with stable refs and display metadata. Evidence: `IG_REFERENCE_AOL_GRAPH_AND_GUIDANCE_IMPLEMENTATION_PLAN_2026-05-02.md:L59-L87`.
- Current code already has a bottom pane named `Meeting Graph`, a graph shell anchor, canvas zoom/pan, flow/runs/trace mode controls, inspector tabs, command bar, object graph fetch, execution graph fetch, and legacy command dispatch. Evidence: `AddressableObjectHostShell.tsx:L557-L1052`, `AOLMeetingBottomShell.tsx:L1944-L2465`, `AOLMeetingBottomShell.tsx:L3076-L3339`, `AOLMeetingBottomShell.tsx:L3909-L4129`.
- Current IG reference cards already expose addressable-object entry, quick scene preview, add seed, batch pin, source account/post links, and more actions. Evidence: `ReferenceGridCard.tsx:L198-L326`, `ReferenceGridCard.tsx:L550-L618`.

## Status Legend

| Status | Meaning |
| --- | --- |
| Existing | Present in current local-core or IG UI code, but may need relabeling, rerouting, or command-ledger integration. |
| P0 Target | Required for the productized AOL Runtime Workbench / Meeting Workbench implementation. |
| Pack-Owned | Semantics are supplied by a capability pack; local-core renders the generic shell and command route. |
| Advanced | Available under Trace/Debug/Raw views, not default Work mode. |
| Legacy | Current behavior may remain only as a compatibility path until command-ledger routing lands. |

## Canonical Runtime Objects

| Runtime object | Required responsibility |
| --- | --- |
| `ObjectRef` | Stable reference to an addressable object: owner, kind, id, workspace scope, optional display metadata. |
| `SessionObject` | Object attached to a meeting session with role: target, source, evidence, constraint, output, or review. |
| `MeetingCommandEnvelope` | Server-canonical command submission. It is the canonical operation record. |
| `MeetingCommandStore` row | Persisted ledger entry with status and execution pointer. |
| `AOLCanvasProjection` | Product canvas projection from command ledger, execution graph, object relations, artifacts, proposals, and degraded proof. |
| `GuidanceState` | Pack-owned meeting guidance projection that can produce Guidance/Next/Blocked nodes and command templates. |
| `GuidanceCard` | Pack-owned suggestion with reason, required roles, command template, write mode, and warnings. |
| `Artifact` | Produced asset, tool output, file, generated image, summary, or external result persisted with provenance. |
| `Proposal` | Staged change requiring review before canonical promotion. |
| `ReviewRoute` | Reviewable route from proposal/output to approve, request changes, reject, or promote. |
| `AOLNotification` | Session-visible update after accepted/running/completed/failed/review/asset events. |

## Shared State Machines

### Command State

```text
draft -> accepted -> running -> completed
                 \-> failed
                 \-> needs_review -> completed
                 \-> superseded
```

### Object Attachment State

```text
unresolved mention -> resolved ObjectRef -> attached SessionObject -> selected focus
```

### Asset Landing State

```text
none -> staged runtime output -> persisted artifact/proposal -> review route -> canonical promotion
```

### Notification State

```text
silent draft -> accepted toast/ledger row -> running progress -> completion/failure/review notification
```

## UX/UI Action Catalog

Each action below uses the same sequence columns. `Asset landing` is `none` when the operation only changes view/session state.

### 1. Shell And Session Actions

| Action ID | Status | User intent | UX/UI operation | AOL session feedback | Meeting execution | Asset landing | AOL session notification |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `SHELL_OPEN_OBJECT_TOOL` | Existing/P0 Target | Open the object work controls from a pack surface. | Click the global object/tool anchor. | Shell opens or focuses the object tool panel with current object candidates. | None until object is attached or command is submitted. | none | Optional: `Object tool opened`. |
| `SHELL_OPEN_WORK_SESSION` | Existing/P0 Target | Inspect how the current object is being used by the meeting. | Click graph/session anchor; open AOL Runtime Workbench with `Meeting Workbench` view. | Bottom shell opens in default mode; Context Bar shows focus, status, runtime, next step, and missing context. | Fetch meeting summary, command ledger, execution graph, object graph projection, and guidance projection. | none | `Session loaded` or `No active session`. |
| `SHELL_START_SESSION` | P0 Target | Start a collaborative work session when no meeting exists. | Click `Start session` from disabled Command Dock or Context Bar. | New session id appears; command dock becomes enabled. | Create/reuse `MeetingSession.id` without a second lifecycle namespace. | session metadata | `Meeting Workbench started`. |
| `SHELL_CLOSE_SESSION_PANE` | Existing/P0 Target | Return to primary pack workflow without losing session state. | Click close icon in shell header. | Pane closes; session state remains in backend. | None. | none | none, unless running command remains active. |
| `SHELL_SET_COMPACT_MODE` | Existing/P0 Target | Make the session a narrow assistant panel. | Click compact pane icon. | Inspector collapses behind rail, Object Outliner becomes drawer, Command Dock remains visible. | None. | none | none. |
| `SHELL_SET_DEFAULT_MODE` | Existing/P0 Target | Use normal split workspace. | Click default pane icon. | Four-editor layout returns to default dimensions. | None. | none | none. |
| `SHELL_SET_EXPANDED_MODE` | Existing/P0 Target | Review flow or generated outcomes with more canvas room. | Click expanded pane icon. | Canvas expands; inspector width is user-resizable within target range. | None. | none | none. |
| `SHELL_DRAG_RESIZE` | P0 Target | Adjust workbench height or inspector width. | Drag pane handle or inspector boundary. | Layout dimensions update without changing selected object/command. | None. | none | none. |
| `SHELL_VIEW_WORK` | P0 Target | Work with product-level objects and outcomes. | Select `Work` in Context Bar. | Canvas hides raw node/trace counts and renders selected subgraph. | Reads command ledger and product projection. | none | none. |
| `SHELL_SELECT_NEXT_STEP` | P0 Target | Jump to what the AI says should happen next. | Click Context Bar next-step chip. | Canvas selects the corresponding `Next`, `Guidance`, or `Blocked` node; Inspector opens Guidance or Runtime. | Reads guidance/command projection; no execution until command submit. | none | none. |
| `SHELL_SELECT_MISSING_CONTEXT` | P0 Target | Resolve why the next command cannot run yet. | Click Context Bar missing-context chip. | Outliner highlights the missing role placeholder and Command Dock mention picker can open. | No dispatch. | none | `Missing context selected`. |
| `SHELL_VIEW_TRACE` | Existing/P0 Target | Inspect execution provenance. | Select `Trace`. | Trace inspector/canvas scope opens; raw replay events remain secondary. | Fetch or reveal execution graph/events. | none | none. |
| `SHELL_VIEW_DEBUG` | Existing/P0 Target | Diagnose graph/node projection issues. | Select `Debug`. | Raw lane board, node count, trace count, and JSON are available. | Fetch debug payloads. | none | none. |
| `SESSION_SELECT_LEDGER_ROW` | P0 Target | Revisit an earlier instruction. | Click command ledger row. | Selected command becomes canvas focus; inspector opens Summary/Runtime for it. | Reads ledger row and related execution/artifact proof. | none | none. |
| `SESSION_SELECT_RECENT` | Existing/P0 Target | Switch between active/recent sessions. | Click session strip/card in shell. | Session id, object list, ledger, canvas, and inspector update. | Fetch selected meeting/session payloads. | none | `Session changed`. |

### 2. Object Selection And Attachment Actions

| Action ID | Status | User intent | UX/UI operation | AOL session feedback | Meeting execution | Asset landing | AOL session notification |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `OBJECT_REQUEST_TARGETING` | Existing/P0 Target | Select an object from the current workbench as command context. | Click object-targeting control. | Host shell enters targeting mode and highlights eligible objects. | None. | none | `Select an object to attach`. |
| `OBJECT_CANCEL_TARGETING` | Existing/P0 Target | Stop selecting an object. | Click cancel targeting or press Escape. | Targeting highlights clear; previous focus remains. | None. | none | none. |
| `OBJECT_SELECT_CANDIDATE` | Existing/P0 Target | Attach one of the detected object candidates. | Click an object candidate. | Candidate resolves to `ObjectRef`; role picker becomes active. | None until attach. | none | `Object selected`. |
| `OBJECT_SET_ROLE_TARGET` | Existing/P0 Target | Mark object as the main target. | Select role `Target`. | Object appears under Outliner `Target`; focus chip updates. | Session attach/update call. | session object metadata | `Target attached`. |
| `OBJECT_SET_ROLE_SOURCE` | Existing/P0 Target | Use object as creative/source input. | Select role `Source`. | Object appears under Outliner `Sources`; guidance can suggest source-driven commands. | Session attach/update call. | session object metadata | `Source attached`. |
| `OBJECT_SET_ROLE_EVIDENCE` | P0 Target | Attach object as proof or reference material. | Select role `Evidence`. | Object appears under Outliner `Evidence`. | Session attach/update call. | session object metadata | `Evidence attached`. |
| `OBJECT_SET_ROLE_CONSTRAINT` | P0 Target | Add a rule, brand constraint, or requirement. | Select role `Constraint`. | Object appears under Outliner `Constraints`. | Session attach/update call. | session object metadata | `Constraint attached`. |
| `OBJECT_SET_ROLE_OUTPUT` | P0 Target | Attach an output as produced context. | Select role `Output`. | Object appears under Outliner `Outputs`. | Session attach/update call, usually after artifact/proposal creation. | session object metadata | `Output attached`. |
| `OBJECT_SET_ROLE_REVIEW` | P0 Target | Attach a review route or decision. | Select role `Review`. | Object appears under Outliner `Review`. | Session attach/update call. | session object metadata | `Review route attached`. |
| `OBJECT_ATTACH_CURRENT` | Existing/P0 Target | Attach the current object without leaving the surface. | Click attach/pin current object. | Object appears in Outliner with selected role; canvas refreshes selected object subgraph. | Session attach/update call; object graph projection can refresh. | session object metadata | `Object attached to session`. |
| `OBJECT_OPEN_OWNER` | Existing/P0 Target | Jump back to the pack-native detail surface. | Use row secondary menu `Open owner`. | Owner surface opens or focuses; AOL session remains available. | None. | none | none. |
| `OBJECT_INSERT_MENTION` | P0 Target | Reference an object in a typed instruction. | Use row secondary menu `Insert mention` or click mention icon. | `@owner.kind:id` chip/text is inserted into active draft. | None until submit. | none | Draft ledger row may update locally. |
| `OBJECT_REMOVE_FROM_SESSION` | P0 Target | Remove irrelevant context. | Use row secondary menu `Remove from session`. | Object row disappears; canvas and guidance recompute. | Session detach/update call. | session object metadata | `Object removed from session`. |
| `OBJECT_SELECT_IN_OUTLINER` | P0 Target | Inspect object role, relations, and suggested commands. | Click object row in Object Outliner. | Canvas focuses `object -> guidance -> commands -> outputs/reviews`; inspector opens Summary. | Fetch bounded object relations and guidance if stale. | none | none. |
| `OBJECT_SELECT_MISSING_ROLE` | P0 Target | Fill a role required by guidance. | Click a missing-role placeholder such as `Missing target`. | Mention picker or object targeting opens with the required role preselected. | No dispatch until object attach and command submit. | none | `Select object for missing role`. |
| `OBJECT_SELECT_IN_CANVAS` | Existing/P0 Target | Inspect an object node already visible in the flow. | Click object node in Semantic Flow Canvas. | Same selection state as Outliner; inspector updates. | None unless lazy data fetch is needed. | none | none. |

### 3. Pack Surface And IG Reference Actions

| Action ID | Status | User intent | UX/UI operation | AOL session feedback | Meeting execution | Asset landing | AOL session notification |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `IG_REFERENCE_CARD_SELECT` | Existing/P0 Target | Inspect one IG reference. | Click card body. | Pack surface selection changes; if AOL session is open, object candidate can become current focus. | None. | none | none. |
| `IG_REFERENCE_MULTI_SELECT_TOGGLE` | Existing/P0 Target | Build a set of source references. | Toggle card checkbox. | Pack selection count updates; AOL session may offer bulk attach/template suggestions. | None until attach/template/submit. | none | none. |
| `IG_REFERENCE_OPEN_AOL_ACTIONS` | Existing/P0 Target | Use this reference inside AOL. | Click small AOL/object affordance on the card. | AOL Runtime Workbench opens Meeting Workbench view with `@ig.reference:{id}` as candidate/focus. | None until attach or command submit. | none | `Reference ready for session`. |
| `IG_REFERENCE_INSERT_MENTION` | P0 Target/Pack-Owned | Reference this IG image in a command. | Click insert mention from card menu or guidance. | Command Dock receives `@ig.reference:{id}`. | None until submit. | none | Draft updated. |
| `IG_REFERENCE_ATTACH_SOURCE` | P0 Target/Pack-Owned | Use this reference as a session source. | Click attach/pin from card menu or Object Tool with role `Source`. | Outliner shows the reference under `Sources`; guidance recomputes. | Session attach/update call. | session object metadata | `IG reference attached as source`. |
| `IG_REFERENCE_OPEN_SOURCE_ACCOUNT` | Existing/Pack-Owned | Inspect the source account. | Click source account link. | Owner/pack surface opens account context; AOL session remains unchanged. | None. | none | none. |
| `IG_REFERENCE_OPEN_SOURCE_POST` | Existing/Pack-Owned | Inspect provenance post. | Click source post/permalink link. | External or owner detail opens; provenance remains available in Relations. | None. | none | none. |
| `IG_REFERENCE_PREVIEW_SCENE_TEMPLATE` | Existing -> P0 Target | Turn a reference into a scene preview instruction. | Existing quick preview affordance becomes `Insert command template`. | Command Dock receives template such as `/stage @ig.reference:{id} as source for @target`. | None until submit. | none | Draft updated with missing target warning if needed. |
| `IG_REFERENCE_CREATE_TRAINING_CANDIDATE_TEMPLATE` | Existing -> P0 Target | Create a training candidate from the reference. | Existing add-seed/training affordance becomes template insertion in active command. | Dock shows `/stage @ig.reference:{id} as source` or pack-defined template. | Submit creates command ledger row and pack runtime execution. | staged artifact/proposal depending write mode | Accepted/running/completed or needs-review notification. |
| `IG_REFERENCE_REGISTER_SOURCE_SEED_TEMPLATE` | Existing -> P0 Target | Queue or register a source account seed. | Existing batch-pin/register behavior becomes command template when inside AOL session. | Dock receives a command with source account mention/bounded ref. | Submit dispatches through command API to IG pack tool/playbook. | task/proposal/pack-owned artifact | `Seed registration staged` or `Review required`. |
| `IG_REFERENCE_MORE_MENU` | Existing/P0 Target | Access secondary pack actions without cluttering card. | Open card more menu. | Menu offers owner detail, insert mention, attach/pin, and templates only. | None until command submit. | none | none. |
| `IG_REFERENCE_GUIDANCE_REFRESH` | P0 Target/Pack-Owned | Ask what this reference can do in the session. | Select reference, open Inspector `Guidance`, or attach reference. | Guidance cards show templates, missing context, warnings, and suggested mentions. | Calls pack-owned guidance tool/playbook if stale. | none | `Guidance refreshed` only on explicit refresh or error. |

### 4. Command Dock And Command Ledger Actions

| Action ID | Status | User intent | UX/UI operation | AOL session feedback | Meeting execution | Asset landing | AOL session notification |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `COMMAND_TYPE_TEXT` | Existing/P0 Target | Express a new instruction. | Type in Command Dock. | Draft state appears; parser can show unresolved mentions and missing roles. | None. | none | none. |
| `COMMAND_OPEN_MENTION_PICKER` | Existing/P0 Target | Reference an object quickly. | Type `@` or click mention control. | Mention picker lists session objects, current object candidates, and searchable objects. | None. | none | none. |
| `COMMAND_APPLY_MENTION` | Existing/P0 Target | Insert a selected object reference. | Select mention option. | Draft receives normalized mention chip/text. | None. | none | Draft updated. |
| `COMMAND_SELECT_PACK_TOOL` | Existing/P0 Target | Override auto-routing only when necessary. | Use pack tool dropdown. | Selected tool appears as secondary routing hint. | Submitted envelope includes requested action metadata. | none until submit | none. |
| `COMMAND_INSERT_TEMPLATE` | P0 Target | Use a suggested operation without hidden dispatch. | Click template from Guidance, Actions, card menu, or command suggestions. | Dock fills slash verb, mentions, expected output, and write mode hints. | None until submit. | none | Draft updated. |
| `COMMAND_EDIT_TEMPLATE` | P0 Target | Adjust target/source/review text before execution. | Edit the inserted template. | Parser revalidates mentions and missing roles. | None. | none | none. |
| `COMMAND_SUBMIT` | Existing -> P0 Target | Execute the instruction through meeting runtime. | Click Send or press Enter. | Optimistic draft becomes pending; backend returns accepted ledger row or validation errors. | POST `MeetingCommandEnvelope`; server resolves mentions, persists command row, dispatches runtime. | command ledger row; later runtime outputs | `Command accepted`, then running/completed/failed/review notifications. |
| `COMMAND_BLOCKED_RUNTIME` | P0 Target | Understand why command cannot run. | Try Send while runtime is unavailable or required refs unresolved. | Send is blocked with clear reason; draft remains editable. | No dispatch. | none | `Blocked: runtime unavailable` or validation reason. |
| `COMMAND_RETRY_FAILED` | P0 Target | Re-run a failed command with same or edited context. | Click retry on failed ledger row. | New draft is created from failed command; original remains immutable. | Submit creates new command row linked to previous id. | new command row, possible artifacts | `Retry accepted` after submit. |
| `COMMAND_SUPERSEDE_DRAFT` | P0 Target | Replace an obsolete draft. | Edit or discard draft after a newer command exists. | Old draft row marked superseded locally/server-side when persisted. | Optional command store update. | command ledger metadata | `Draft superseded` only if persisted. |
| `COMMAND_SELECT_LEDGER_ENTRY` | P0 Target | Inspect status and outputs of a prior command. | Click command ledger entry. | Canvas focuses command impact graph; inspector opens Summary/Runtime/Relations. | Fetch command projection and proof. | none | none. |
| `COMMAND_OPEN_CONSOLE` | Existing/Advanced | Inspect raw command/runtime console. | Toggle console drawer. | Debug console opens below/near dock. | None unless explicit replay tools exist. | none | none. |

### 5. Semantic Flow Canvas Actions

| Action ID | Status | User intent | UX/UI operation | AOL session feedback | Meeting execution | Asset landing | AOL session notification |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `CANVAS_SELECT_OBJECT_NODE` | Existing/P0 Target | Inspect object role and downstream impact. | Click `Object` node. | Object becomes selection; Outliner and Inspector synchronize. | May refresh bounded object graph. | none | none. |
| `CANVAS_SELECT_GUIDANCE_NODE` | P0 Target/Pack-Owned | Understand AI-suggested next steps. | Click `Guidance` or `Next` node. | Inspector opens Guidance, shows reason, required roles, templates, warnings, and no auto-dispatch. | Fetch pack-owned guidance state if stale. | none | none. |
| `CANVAS_SELECT_COMMAND_NODE` | Existing/P0 Target | Inspect an instruction and its runtime path. | Click `Command` node. | Ledger row selection syncs; inspector shows command summary/runtime. | Fetch command proof if not loaded. | none | none. |
| `CANVAS_SELECT_RUN_NODE` | Existing/P0 Target | Inspect tool/executor run. | Click `Run` node. | Inspector Runtime opens with executor/task ids. | Fetch execution details/events. | none | none. |
| `CANVAS_SELECT_OUTCOME_NODE` | Existing/P0 Target | Inspect result summary. | Click `Outcome` node. | Inspector Summary opens outcome details and provenance. | Fetch linked artifact/proposal ids. | none | none. |
| `CANVAS_SELECT_ARTIFACT_NODE` | Existing/P0 Target | Open generated asset. | Click `Artifact` node. | Inspector shows artifact preview, provenance, and owner link. | Fetch artifact metadata/content preview. | none | none. |
| `CANVAS_SELECT_PROPOSAL_NODE` | P0 Target | Review staged change. | Click `Proposal` node. | Inspector opens Review route and proposed diff/output. | Fetch proposal/review data. | none | `Review required` if not already shown. |
| `CANVAS_SELECT_REVIEW_NODE` | P0 Target | See decision status. | Click `Review` node. | Inspector shows reviewer, decision, comments, promotion state. | Fetch review route. | none | none. |
| `CANVAS_SELECT_BLOCKED_NODE` | P0 Target | Understand why execution/proof is degraded. | Click `Blocked` node. | Inspector shows missing evidence/recovery action. | None or fetch diagnostics. | none | `Evidence degraded` if newly detected. |
| `CANVAS_EXPAND_CONTEXT` | P0 Target | See related surrounding objects without changing focus. | Toggle context expansion. | Muted unrelated nodes appear around selected subgraph. | Fetch extra relation window if needed. | none | none. |
| `CANVAS_COLLAPSE_CONTEXT` | P0 Target | Return to focused view. | Toggle context expansion off. | Canvas returns to selected subgraph only. | None. | none | none. |
| `CANVAS_PAN` | Existing/P0 Target | Navigate large canvas. | Drag canvas background. | Viewport pans; selection remains stable. | None. | none | none. |
| `CANVAS_ZOOM_IN` | Existing/P0 Target | Inspect details. | Click zoom in or mouse wheel. | Canvas zoom increases within bounds. | None. | none | none. |
| `CANVAS_ZOOM_OUT` | Existing/P0 Target | See more of the flow. | Click zoom out or mouse wheel. | Canvas zoom decreases within bounds. | None. | none | none. |
| `CANVAS_FIT_VIEW` | Existing/P0 Target | Recenter after navigation. | Click fit/reset view. | Selected subgraph fits viewport. | None. | none | none. |

### 6. Inspector Actions

| Action ID | Status | User intent | UX/UI operation | AOL session feedback | Meeting execution | Asset landing | AOL session notification |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `INSPECTOR_OPEN_SUMMARY` | Existing/P0 Target | Understand selected object/command quickly. | Click `Summary` tab. | Shows title, role, status, short description, outputs/reviews. | Fetch summary if stale. | none | none. |
| `INSPECTOR_OPEN_GUIDANCE` | P0 Target/Pack-Owned | See useful next commands. | Click `Guidance` tab. | Pack guidance cards, missing context, templates, warnings appear. | Calls guidance tool/playbook if stale. | none | Guidance refresh/error notification only when explicit. |
| `INSPECTOR_INSERT_GUIDANCE_TEMPLATE` | P0 Target/Pack-Owned | Use a suggested next action. | Click a guidance card template insert control. | Command Dock receives template; missing roles are highlighted. | None until submit. | none | Draft updated. |
| `INSPECTOR_OPEN_ACTIONS` | P0 Target | See generic operations available for selected item. | Click `Actions` tab. | Shows generic verbs/templates and owner-surface link. | None until template submit. | none | none. |
| `INSPECTOR_INSERT_ACTION_TEMPLATE` | P0 Target | Start an operation from a generic action. | Click `Insert command template`. | Dock receives slash verb and selected object mention. | None until submit. | none | Draft updated. |
| `INSPECTOR_OPEN_RELATIONS` | Existing/P0 Target | Inspect bounded object relations. | Click `Relations` tab. | Relation kind, direction, target title/status, and expandable flag render. | Calls `/object-graph/project` if stale. | none | `Relations unavailable` only on error. |
| `INSPECTOR_SELECT_RELATION_TARGET` | P0 Target | Move focus to a related object. | Click expandable relation target. | If first-class target, selection moves; if bounded display target, detail stays read-only. | Fetch relation target projection if expandable. | none | none or `Target is display-only`. |
| `INSPECTOR_OPEN_RUNTIME` | Existing/P0 Target | See executor, status, and ids. | Click `Runtime` tab. | Shows executor/runtime, command status, task/execution ids. | Fetch runtime status if stale. | none | none. |
| `INSPECTOR_OPEN_TRACE` | Existing/Advanced | Inspect raw replay events. | Click advanced `Trace` tab. | Trace events and filters become visible. | Fetch trace payload if needed. | none | none. |
| `INSPECTOR_OPEN_RAW` | Existing/Advanced | Inspect JSON/debug payload. | Click advanced `Raw` tab. | Raw JSON appears behind advanced view. | Fetch raw payload if needed. | none | none. |
| `INSPECTOR_CLOSE` | Existing/P0 Target | Give canvas more room. | Click close inspector or rail active tab. | Inspector collapses; selection remains. | None. | none | none. |

### 7. Meeting Execution And Asset Landing Actions

These are user-visible runtime transitions. Some are triggered by backend events rather than direct UI clicks, but they must be rendered as AOL session feedback because they close the loop from command to durable asset.

| Action ID | Status | User intent | UX/UI operation | AOL session feedback | Meeting execution | Asset landing | AOL session notification |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `EXECUTION_ACCEPTED` | P0 Target | Know the command was accepted. | User submits command; backend accepts. | Ledger row status becomes `accepted`; canvas creates command node. | Command row persisted and dispatch begins. | command ledger row | `Command accepted`. |
| `EXECUTION_RUNNING` | Existing -> P0 Target | Track work in progress. | Runtime emits running/update event. | Canvas highlights `command -> run`; Runtime tab shows executor/task id. | Tool/playbook/external agent is running. | task/execution pointer | `Command running`. |
| `EXECUTION_PROGRESS` | P0 Target | See intermediate progress without raw trace. | Runtime emits progress event. | Ledger row or run node updates compact progress/status. | Existing event stream or polling updates projection. | task/execution metadata | Optional progress notification for long tasks only. |
| `EXECUTION_TOOL_RESULT` | Existing -> P0 Target | Inspect returned tool data. | Runtime completes a tool step. | Outcome node appears with provenance. | Tool result attaches to command proof. | staged runtime output | none unless user action needed. |
| `EXECUTION_ARTIFACT_CREATED` | Existing -> P0 Target | Use generated output. | Runtime produces durable artifact. | Artifact node appears under selected command and Outliner `Outputs`. | Artifact is persisted and linked to command/session/object refs. | artifact record | `Asset landed`. |
| `EXECUTION_PROPOSAL_STAGED` | P0 Target | Review proposed changes before canonical write. | Runtime stages proposal under review mode. | Proposal and Review nodes appear; Inspector opens Review route if active. | Proposal persisted with provenance and write mode. | proposal record + review route | `Review required`. |
| `EXECUTION_FAILED` | Existing -> P0 Target | Understand and recover from failure. | Runtime returns error/failure. | Ledger row status becomes `failed`; Blocked node shows reason and retry template. | Failure evidence attached to command row. | command error metadata | `Command failed`. |
| `EXECUTION_DEGRADED_PROOF` | P0 Target | See when graph proof is incomplete. | Projection cannot attach full evidence. | Blocked/degraded node appears with clear reason. | Relation-only or fallback metadata is used. | degraded proof metadata | `Evidence degraded`. |
| `ASSET_OPEN_OWNER` | P0 Target | Inspect the durable output in its owner surface. | Click owner link from artifact/proposal inspector. | Owner surface opens; AOL session remains in context. | None. | none | none. |
| `ASSET_ATTACH_AS_OUTPUT` | P0 Target | Keep output visible in session context. | Click attach output or auto-attach after creation. | Artifact appears under Outliner `Outputs`. | Session attach/update call. | session object metadata | `Output attached`. |

### 8. Review And Promotion Actions

| Action ID | Status | User intent | UX/UI operation | AOL session feedback | Meeting execution | Asset landing | AOL session notification |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `REVIEW_OPEN_ROUTE` | P0 Target | Review staged proposal or generated asset. | Click Review node, review route, or `Needs review` ledger state. | Inspector Review/Summary displays proposal, provenance, and decision controls. | Fetch review route/proposal metadata. | none | none. |
| `REVIEW_APPROVE` | P0 Target | Accept staged output. | Click approve in review route. | Review node updates to approved; command may complete. | Review decision persisted; promotion may start if configured. | review decision | `Proposal approved`. |
| `REVIEW_REQUEST_CHANGES` | P0 Target | Ask agent/pack to revise. | Click request changes and type notes. | New command draft/template is created referencing proposal and review notes. | Submit creates new command row linked to proposal. | review decision + new command draft | `Changes requested`. |
| `REVIEW_REJECT` | P0 Target | Reject unsuitable output. | Click reject with optional reason. | Review node updates rejected; proposal remains as historical artifact. | Review decision persisted; no canonical promotion. | review decision | `Proposal rejected`. |
| `REVIEW_PROMOTE_CANONICAL` | P0 Target | Promote approved proposal into canonical asset/store. | Click promote or approve-with-promote depending policy. | Canvas shows `proposal -> promotes -> artifact/object`; Outliner Outputs updates. | Promotion job/write path runs through owner pack/runtime. | canonical asset/object record | `Promoted to canonical asset`. |
| `REVIEW_OPEN_PROVENANCE` | P0 Target | Audit why this proposal exists. | Click provenance link in review inspector. | Canvas focuses source command/object subgraph. | Fetch source proof if stale. | none | none. |

### 9. Notification Actions And Session Feedback

| Action ID | Status | User intent | UX/UI operation | AOL session feedback | Meeting execution | Asset landing | AOL session notification |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `NOTIFY_COMMAND_ACCEPTED` | P0 Target | Confirm instruction was received. | Triggered after command API acceptance. | Ledger row moves from draft to accepted. | Command store persisted. | command row | Toast/banner and ledger status. |
| `NOTIFY_COMMAND_RUNNING` | P0 Target | See that runtime started. | Triggered by runtime dispatch/update. | Context Bar status `Running`; canvas highlights run path. | Runtime task has execution pointer. | task metadata | Running indicator. |
| `NOTIFY_COMMAND_COMPLETED` | P0 Target | Know work finished. | Triggered by completion event/poll. | Ledger row completed; Outcome/Artifact nodes visible. | Runtime complete. | artifact/proof metadata if produced | Completion notification with output link. |
| `NOTIFY_COMMAND_FAILED` | P0 Target | Recover from failure. | Triggered by failure event/poll. | Failed row and Blocked node appear; retry template suggested. | Failure stored on command/runtime proof. | error metadata | Failure notification with reason. |
| `NOTIFY_REVIEW_REQUIRED` | P0 Target | Decide staged output. | Triggered by proposal/review route creation. | Context Bar status `Needs review`; Review node appears. | Proposal persisted; review route open. | proposal + review route | Review-required notification. |
| `NOTIFY_ASSET_LANDED` | P0 Target | Confirm durable asset exists. | Triggered after artifact persistence. | Artifact node and Outliner Output row appear. | Artifact linked to command/session/object refs. | artifact record | Asset-landed notification. |
| `NOTIFY_DEGRADED_EVIDENCE` | P0 Target | Know why graph proof is incomplete. | Triggered by projection fallback. | Blocked/degraded node visible; Inspector explains missing proof. | Projection uses fallback relation/metadata. | degraded proof metadata | Evidence-degraded notification. |
| `NOTIFY_RUNTIME_UNAVAILABLE` | P0 Target | Avoid sending impossible work. | Runtime health says unavailable. | Context Bar runtime chip blocked; Send disabled except drafts. | No execution dispatch. | none | Runtime-unavailable notification. |
| `NOTIFY_RELATIONS_UNAVAILABLE` | P0 Target | Understand object graph missing data. | Object graph projection fails. | Relations tab shows error; canvas keeps command view usable. | `/object-graph/project` failed or returned degraded data. | none | Relations-unavailable notice. |
| `NOTIFY_GUIDANCE_UNAVAILABLE` | P0 Target/Pack-Owned | Understand missing pack guidance. | Guidance tool fails or is not installed. | Guidance tab shows unavailable state; command dock still accepts manual text. | Guidance call failed. | none | Guidance-unavailable notice. |

## Canonical End-To-End Walkthroughs

### Flow A: Use IG Reference As Source For A Target Scene

| Step | Sequence |
| --- | --- |
| Intent | User wants to use an IG reference as style/source material for a target scene. |
| UX/UI operation | User opens IG reference AOL affordance, attaches it as `Source`, inserts or accepts `/stage @ig.reference:{id} as source for @target`. |
| AOL feedback | Object Outliner shows the reference under `Sources`; Command Dock highlights missing `@target` until provided. |
| Meeting execution | User submits; backend persists `MeetingCommandEnvelope`; runtime dispatches pack guidance/generation path. |
| Asset landing | Runtime creates staged output or proposal linked to command id, source ref, and target ref. |
| Notification | AOL session shows accepted/running/completed or needs-review; canvas shows `source -> command -> run -> proposal/artifact`. |

### Flow B: Create Training Candidate From IG Reference

| Step | Sequence |
| --- | --- |
| Intent | User wants the reference promoted into a training-candidate workflow. |
| UX/UI operation | User selects reference, opens Inspector Guidance, inserts `create training candidate` template, edits notes, submits. |
| AOL feedback | Ledger row appears; canvas focuses `command -> run`; Inspector Runtime shows executor/task id. |
| Meeting execution | Command route resolves `@ig.reference:{id}`, validates workspace, dispatches IG pack tool/playbook. |
| Asset landing | IG pack persists training candidate as first-class export or bounded proposal according to target policy. |
| Notification | Session receives `Asset landed` or `Review required`; Outliner `Outputs` updates. |

### Flow C: Review And Promote A Generated Proposal

| Step | Sequence |
| --- | --- |
| Intent | User wants to approve a generated output into the canonical asset store. |
| UX/UI operation | User clicks Review node, inspects provenance, clicks approve/promote. |
| AOL feedback | Review node changes state; canvas shows promotion edge. |
| Meeting execution | Review decision is persisted; promotion job/write path runs through owner pack/runtime. |
| Asset landing | Canonical asset/object record is written and linked to original command/proposal. |
| Notification | Session shows `Promoted to canonical asset`; command status becomes completed if promotion was required. |

### Flow D: Runtime Unavailable But User Still Drafts Work

| Step | Sequence |
| --- | --- |
| Intent | User wants to write the instruction now, even if runtime cannot execute. |
| UX/UI operation | User types command with mentions while Context Bar runtime chip says `No runtime`. |
| AOL feedback | Draft ledger row exists locally or as recommendation-only draft; Send is blocked with reason. |
| Meeting execution | No dispatch until runtime health recovers. |
| Asset landing | none. |
| Notification | Runtime-unavailable notice persists; when runtime recovers, Send becomes available. |

## Pack-Origin UX/UI User Intent Examples

These examples start from a visible pack workbench interaction. Each flow enters the same site-wide AOL Runtime Shell, shows the AOL Runtime Workbench product surface, and selects the Meeting Workbench view rather than creating a pack-private meeting UI.

### IG Workbench Origins

| User intent | IG UX/UI starting point | AOL Runtime Workbench / Meeting Workbench action | Guidance / graph state | Command path | Landing / notification |
| --- | --- | --- | --- | --- | --- |
| Use one IG reference as a style/source input. | User clicks the AOL affordance on an IG reference card. | Open shell, attach `@ig.reference:{id}` as `Source`, focus the source node. | `Guidance` node suggests `use as style source`; `Missing target` appears if no target object exists. | Insert `/stage @ig.reference:{id} as source for @target`; user fills target and submits. | Proposal/artifact lands with source/target refs; notify completed or needs review. |
| Compare multiple IG references before choosing a source. | User multi-selects IG reference cards. | Open shell with selected references under `Sources`; canvas groups them as source candidates. | Guidance shows compare/select-source next step and missing target if needed. | Insert template such as `/recommend sources from @ig.reference:a @ig.reference:b for @target`. | Recommendation output or proposal is attached to Outputs; notify asset landed or review required. |
| Create a training candidate from a reference. | User opens card menu or guidance for selected IG reference. | Shell selects reference and opens `Guidance` node. | Guidance exposes `create training candidate` with required roles/warnings. | Insert pack-owned template; submit through command envelope. | Training-candidate artifact/proposal lands; Outliner shows Output; notify completed/review. |
| Register a source account seed from a reference. | User clicks source account / batch seed affordance in IG references. | Shell receives bounded source-account ref or source reference context. | `Guidance` node shows seed registration and crawl/batch-pin constraints. | Insert `/stage` or pack-owned seed registration template; submit. | Seed registration task/proposal lands; notify queued, completed, or needs review. |
| Inspect why a reference is not ready for generation. | User selects IG reference with missing analysis/training state. | Shell opens Relations/Guidance around the reference. | `Blocked` node explains missing visual analysis, source post, tags, or training annotations. | User can insert recovery template such as inspect analysis gaps; no hidden dispatch. | Recovery task lands or no-op notification explains missing context. |
| Generate or stage a post/scene variant from reference context. | User selects reference and asks for generation in command dock. | Shell keeps reference as Source and asks for Target/Output role if absent. | Guidance proposes generated variant template and write mode. | User submits command; runtime dispatches IG/owner workflow. | Proposal/output lands; review route appears when write mode requires review. |

### PD Workbench Origins

| User intent | PD UX/UI starting point | AOL Runtime Workbench / Meeting Workbench action | Guidance / graph state | Command path | Landing / notification |
| --- | --- | --- | --- | --- | --- |
| Ask what a storyboard scene needs next. | User clicks a storyboard scene's meeting/AOL affordance in PD Workbench. | Open shell, attach `@performance_direction.storyboard_scene:{id}` as `Target`. | `pd_director_guidance` projects `Guidance`, `Next`, and missing-context nodes. | User inserts director guidance template or writes intent with scene mention. | Director guidance state lands; notify guidance refreshed or missing context. |
| Convert creator intent into director guidance. | User enters creator intent in PD and opens AOL Runtime Workbench. | Meeting Workbench view carries creator intent plus selected scene/source attachments. | Guidance node explains director framing, required references, and proposal draft path. | Submit command routed to `pd_director_guidance_compile` or related playbook/tool. | Director guidance cards and proposal materialization draft land in Outputs/Review. |
| Generate a scene package from a PD session. | User selects scene/session and chooses scene package generation template. | Shell focuses Target scene and Source references. | Guidance checks missing source/character/scene scope context. | Insert/submit `pd_scene_package_generate` style command template. | Scene generation metadata lands; notify queued/running/completed. |
| Continue a queued scene package into preview handoff. | User opens a scene generation job/status from PD Workbench. | Shell focuses existing job/output object. | Canvas shows command -> run -> scene package status; `Next` suggests preview handoff when selector exists. | Insert/submit preview handoff command using generated scene package selector. | Preview/handoff artifact lands; notify completed or blocked. |
| Review a storyboard proposal artifact. | User clicks a PD proposal/review route. | Shell focuses proposal under `Review`; canvas shows proposal -> review -> promote path. | Guidance explains approve/request changes/reject/promote options. | User approves, requests changes, rejects, or promotes via review command. | Review decision or canonical storyboard ref lands; notify approved/rejected/promoted. |
| Patch a storyboard scene from generated/reference evidence. | User selects a scene and generated/referenced evidence. | Shell attaches scene as Target and generated/reference assets as Evidence/Sources. | Guidance suggests patch proposal template and required constraints. | Submit `/stage` or PD patch template through command envelope. | Storyboard proposal artifact lands; review route appears. |
| Audit provenance for a generated reels asset. | User opens generated asset from PD Workbench. | Shell focuses generated asset node and relations. | Canvas shows generated_from_source, generated_with_character, and landed_in relations. | User can insert follow-up review/promote/patch template. | No new asset unless submitted; notification only if command runs. |

## Implementation Acceptance Checklist

- Every visible operation maps to one action id in this catalog or is intentionally marked Advanced/Legacy.
- Every Work-view UI element maps to a graph node, graph edge, command envelope, guidance state, runtime event, artifact/proposal, review route, or recovery state.
- Product Work view never exposes raw JSON, trace counts, or node counts as primary UI.
- Guidance must appear as selectable graph state, not only as an Inspector side panel.
- Pack cards do not dispatch hidden generation actions inside AOL mode; they insert mentions/templates or open owner detail.
- `COMMAND_SUBMIT` is the only generic execution entrypoint for user-authored work in the productized session.
- Command ledger rows, canvas nodes, inspector details, and notifications all share the same `command_id`.
- Asset/proposal/review outputs always link back to the source command and source/target object refs.
- Bounded relation targets include enough display metadata to render in canvas/inspector without expanding private pack payloads.
- Degraded proof and runtime unavailable states remain operable: users can inspect cause, draft commands, and recover when dependencies return.

## Open Engineering Edges

- The current shell still labels the pane `Meeting Graph`; implementation must rename the user-facing product/view framing to `AOL Runtime Workbench` / `Meeting Workbench` while keeping debug graph concepts available.
- Current command dispatch still uses legacy UI-built `action_params`; the command API and store must land before the catalog can be fully enforced.
- IG current quick actions must be rerouted in AOL context so they insert command templates instead of bypassing the command ledger.
- Review/promotion persistence requires owner-pack write policies; local-core should render generic review controls but must not invent pack-private write semantics.
- Notifications need one canonical source of truth: command ledger status plus runtime/artifact/review events, not independent UI-only flags.
