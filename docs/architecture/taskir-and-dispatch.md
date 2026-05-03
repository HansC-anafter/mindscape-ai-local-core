# TaskIR and Dispatch

TaskIR is the local intermediate representation for executable work in Mindscape AI Local Core. It lets meeting output, handoff input, playbooks, tools, agent runtimes, artifacts, and dispatch attempts share a structured execution state.

This page describes the released public architecture scope for the current repository.

## TaskIR Model

TaskIR stores:

- task, workspace, actor, and intent identity
- current phase and task status
- ordered or DAG-shaped PhaseIR entries
- produced artifact references
- structured execution metadata for local execution and governance context
- checkpoint and update metadata

PhaseIR stores bounded phase identity, status, dependency, target, actuator, input, attempt, timing, and rollback metadata.

TaskIR can resolve executable phases from dependency state, carry artifact references, update phase status, support actuation planning, and preserve local recovery points.

## Governance Metadata

TaskIR metadata can carry typed governance context such as goals, constraints, acceptance criteria, lens and memory references, provenance, human instructions, context attachments, and requested output type.

Meeting compilation builds this metadata from governed local input or verified handoff intake when available.

## Meeting to TaskIR

The meeting IR compiler turns action intents or compatibility action items into TaskIR phases while preserving dependencies when possible.

If no executable phase exists, the compiler preserves the meeting outcome as a representable decision phase.

Requested artifacts can be emitted into TaskIR during compilation when the current session and action inputs request them.

## Dispatch Orchestrator

The dispatch orchestrator walks the TaskIR graph:

- resolve ready phases from dependency state
- dispatch ready phases through local playbook, tool, or runtime paths
- track phase attempts and dispatch activity
- skip or preserve downstream phases according to failure policy
- write compatibility projections for existing task queries
- allow bounded plan extension when downstream results require it

Dispatch results provide bounded aggregate and per-phase execution state.

## Dispatch Targets

Dispatch can route phases to:

- playbook execution through the execution launcher
- direct tool execution tasks
- workspace agent runtimes
- planned task projections when no actuator is available

Dispatch can also apply workspace routing, upstream result injection, lens context injection, idempotency guards, and provenance snapshots.

## Handoff Intake

Cross-boundary handoff intake can compile verified handoff material into local TaskIR. The intake path resolves local workspace context and persists TaskIR only through Local Core host contracts.

This is a cross-boundary intake surface. It should be documented as a local compile path, not as ownership of any external control plane.

## Persistence and Replay

TaskIR can be persisted through the PostgreSQL TaskIR store after meeting compilation. Handoff handling and execution paths can load TaskIR, update phases, create bounded updates, and continue execution across local playbooks, tools, handoff intake, and planned tasks.

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
