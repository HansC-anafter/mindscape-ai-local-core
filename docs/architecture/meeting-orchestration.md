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

This makes meeting orchestration a control layer around execution, not a chat transcript renderer.

## Meeting Session Lifecycle

Meeting session helpers create or reuse active sessions by local workspace context. They can append agenda items, prepare execution context, persist compiled TaskIR, and close the session with minutes and dispatch state.

Meeting sessions carry bounded metadata for memory selection, workflow evidence, gate results, execution state, dispatch results, and writeback inputs.

## Context Assembly

The meeting engine assembles context from:

- workspace and project state
- runtime profile and route decision
- effective lens state and active intent IDs
- project context and workspace group asset maps
- workflow evidence context
- available playbooks and tools
- uploaded files and conversation state

The prompt layer is one consumer of this context. The same context also feeds policy, action extraction, TaskIR compilation, dispatch, memory writeback, and inspection surfaces.

## Policy Gate and Dispatch Gate

Meeting action items pass through a policy gate before dispatch. The policy gate can block, warn, normalize, or preserve action item metadata before TaskIR compilation.

After policy gating, the dispatch gate evaluates action intents with supervision signals. It can dispatch now, ask for clarification, defer, or shrink scope. Policy-blocked items are not re-evaluated by the dispatch gate.

## Task Decomposition

For dispatchable work, the meeting pipeline can run task decomposition between action intents and TaskIR execution. Decomposition produces bounded PhaseIR structure grounded in available local execution surfaces and may extend a plan when downstream results require it.

Decomposition is a local orchestration detail. Public documentation should describe the boundary, not the private skip heuristics or route shaping rules.

## Finalization and Writeback

Finalization renders meeting minutes, closes the session, emits user-visible meeting output, and records inspection metadata. The session close path can trigger memory writeback through the meeting writeback orchestrator described in the governed memory fabric.

Public documentation should treat meeting orchestration as a governed execution convergence layer. It should not expose internal prompts, private role instructions, private validation transcripts, or provider-specific execution payloads.

## Public Boundary

Local Core owns meeting sessions, meeting orchestration, agenda decomposition, request contract compilation, policy-gated action extraction, TaskIR compilation, dispatch coordination, minutes, session metadata, and writeback hooks.

Local Core does not publicly own:

- provider-native conversation formats
- private deliberation prompts
- external runtime implementation details
- cloud scheduling or billing workflows
- installed capability internals invoked by a meeting result

Public meeting documentation should describe stable local orchestration behavior and leave private prompt, provider, and capability implementation details withheld.
