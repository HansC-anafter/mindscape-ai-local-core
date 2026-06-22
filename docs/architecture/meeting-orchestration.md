# Meeting Orchestration

Mindscape AI Local Core uses meeting orchestration as a governed convergence layer for complex work. A meeting session turns conversation input, handoff input, runtime context, memory, tools, and policy into reviewable decisions, action intents, TaskIR, dispatch results, minutes, and writeback evidence.

This page describes the released public architecture scope for the current repository.

## Meeting Engine

The meeting engine is a bounded orchestrator. It composes local context preparation, governance, action extraction, TaskIR compilation, dispatch coordination, session lifecycle, and tool discovery.

The public pipeline can be described as:

- context and tool preparation
- request contract compilation and governed deliberation
- action intent extraction
- policy and dispatch gate checks
- TaskIR compilation and bounded dispatch
- final minutes, session close, inspection metadata, and writeback hooks

This makes meeting orchestration the control layer that turns discussion into governed execution state.

## Meeting Session Lifecycle

Meeting session helpers create or reuse active sessions by local workspace context. They can append agenda items, prepare execution context, persist compiled TaskIR, and close the session with minutes and dispatch state.

Meeting sessions carry bounded metadata for memory selection, workflow evidence, gate results, execution state, dispatch results, and writeback inputs.

## Context Assembly

The meeting engine assembles context from:

- workspace and project state
- runtime profile and local routing decision
- effective lens state and active intent IDs
- project context and workspace group asset maps
- workflow evidence context
- available playbooks and tools
- uploaded files and conversation state

Assembly paths are one consumer of this context. The same context also feeds policy, action extraction, TaskIR compilation, dispatch, memory writeback, and inspection surfaces.

## Policy Gate and Dispatch Gate

Meeting action items pass through a policy gate before dispatch. The policy gate can block, warn, normalize, or preserve action item metadata before TaskIR compilation.

After policy gating, the dispatch gate evaluates action intents with supervision signals. It can dispatch now, ask for clarification, defer, or shrink scope. Policy-blocked items stay recorded with their gate result.

## Task Decomposition

For dispatchable work, the meeting pipeline can run task decomposition between action intents and TaskIR execution. Decomposition produces bounded PhaseIR structure grounded in available local execution surfaces and may extend a plan when downstream results require it.

Decomposition is a local orchestration detail. Public documentation describes the boundary and released TaskIR behavior.

## Finalization and Writeback

Finalization renders meeting minutes, closes the session, emits user-visible meeting output, and records inspection metadata. The session close path can trigger memory writeback through the meeting writeback orchestrator described in the governed memory fabric.

Public documentation treats meeting orchestration as a governed execution convergence layer. Assembly text, role instructions, validation transcripts, and adapter payloads stay in owner-managed records.

## Public Boundary

Local Core owns meeting sessions, meeting orchestration, agenda decomposition, request contract compilation, policy-gated action extraction, TaskIR compilation, dispatch coordination, minutes, session metadata, and writeback hooks.

Related owners keep:

- adapter conversation formats
- deliberation assembly text
- external runtime implementation details
- managed scheduling workflows
- installed capability internals invoked by a meeting result

Public meeting documentation describes stable local orchestration behavior, gate outcomes, TaskIR compilation, dispatch coordination, and writeback hooks.
