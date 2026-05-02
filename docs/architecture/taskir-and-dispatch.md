# TaskIR and Dispatch

TaskIR is the local intermediate representation for executable work in Mindscape AI Local Core. It lets meeting output, handoff input, playbooks, tools, agent runtimes, artifacts, and dispatch attempts share a structured execution state.

This page describes the released public architecture scope for the current repository.

## TaskIR Model

TaskIR stores:

- task identity, workspace identity, actor identity, and intent instance identity
- current phase and task status
- ordered or DAG-shaped PhaseIR entries
- produced artifact references
- structured execution metadata for intent, execution, cloud compatibility, and governance context
- checkpoint snapshots and update payloads

PhaseIR stores phase identity, status, preferred engine, actual executor, dependencies, target workspace, asset references, tool name, input parameters, dispatch attempt IDs, capability profile, timing, and rollback fields.

TaskIR can compute executable phases from dependency state, add artifacts, update phase status, lower phases into an actuation plan, and create or restore checkpoints.

## Governance Metadata

TaskIR metadata can carry a typed governance context with goals, non-goals, deliverables, constraints, acceptance tests, risk notes, lens snapshot references, memory references, handoff IDs, trace IDs, human instructions, context attachments, and requested output type.

Meeting compilation builds this metadata from `HandoffIn` when present, or from a compiled request contract when available.

## Meeting to TaskIR

The meeting IR compiler turns action intents or legacy action items into TaskIR phases. With action intents, phase IDs match intent IDs and dependencies pass through directly. With legacy action items, the compiler preserves backward compatibility and can create sequential fallback phases.

If no phase exists, the compiler creates a decision phase so the meeting outcome remains representable.

Requested capability artifacts can be emitted into TaskIR during compilation when the current session and action inputs request them.

## Dispatch Orchestrator

The dispatch orchestrator walks the TaskIR DAG:

- build dependency graph and in-degree counts from PhaseIR dependencies
- dispatch all ready phases concurrently
- skip downstream phases when upstream dependencies fail under the default policy
- create and track PhaseAttempt records
- publish dispatch activity events
- write projections for backward-compatible task queries
- allow a supervisor callback to inject new phases after a dispatch wave

Dispatch results include aggregate status, succeeded, failed, skipped, involved workspaces, attempts, and per-phase results.

## Dispatch Targets

Dispatch can route phases to:

- playbook execution through the execution launcher
- direct tool execution tasks
- workspace agent runtimes
- planned task projections when no actuator is available

Dispatch can also apply target workspace routing, upstream phase result injection, lens context injection, idempotency guards, playbook alias rescue, model override resolution through capability profiles, and IR provenance snapshots.

## Handoff Intake

The handoff bundle route can package, verify, intake, and compile signed handoff payloads. The compile path verifies the bundle, extracts a `HandoffIn`, resolves workspace context, obtains an ingress route decision, runs meeting compilation, and persists TaskIR.

This is a cross-boundary intake surface. It should be documented as a local compile path, not as ownership of any external control plane.

## Persistence and Replay

TaskIR can be persisted through the PostgreSQL TaskIR store with replace semantics after meeting compilation. Handoff handling and execution adapters can load TaskIR, update phases, create updates, and continue execution across playbooks, skills, MCP-style handoff surfaces, and planned local tasks.

Public documentation should describe the stable TaskIR shape and dispatch responsibility. It should not publish internal prompt formats, private provider payloads, or low-level adapter implementation plans.

## Public Boundary

Local Core owns TaskIR, PhaseIR, dispatch orchestration, phase attempts, local task projection, handoff intake compilation, and local artifact references.

Local Core does not publicly own:

- external executor internals
- provider-specific payload schemas
- cloud tenant or billing workflow state
- private adapter transport details
- installed capability implementation internals

Public TaskIR documentation should describe the local execution contract and dispatch boundaries without exposing private operational payloads.
