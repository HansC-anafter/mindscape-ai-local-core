# Meeting Orchestration

Mindscape AI Local Core uses meeting orchestration as a governed convergence layer for complex work. A meeting session turns conversation input, handoff input, runtime context, memory, tools, and policy into reviewable decisions, action intents, TaskIR, dispatch results, minutes, and writeback evidence.

This page describes the released public architecture scope for the current repository.

## Meeting Engine

The meeting engine is a bounded multi-role orchestrator. It composes modules for events, governance, prompt inputs, action extraction, generation, dispatch helpers, TaskIR compilation, session lifecycle, and tool discovery.

The public pipeline can be described as:

- context and tool preparation
- request contract compilation and deliberation
- action intent extraction
- policy and dispatch gate checks
- TaskIR compilation, task decomposition when allowed, and DAG dispatch
- final minutes, session close, inspection metadata, and writeback hooks

This makes meeting orchestration a control layer around execution, not a chat transcript renderer.

## Meeting Session Lifecycle

Meeting session helpers create or reuse active sessions by workspace, thread, project, and optional explicit session ID. They can append agenda items, extract `HandoffIn` payloads, build an execution launcher, persist compiled TaskIR, and close the session with minutes and dispatch state.

Meeting sessions carry metadata for selected memory packets, workflow evidence diagnostics, policy gate results, execution IDs, dispatch results, and writeback inputs.

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

For dispatchable work, the meeting pipeline can run a task decomposer between action intents and TaskIR execution. The decomposer creates a PhaseIR DAG grounded in available playbooks and tools. It can also extend the plan after a dispatch wave when downstream results require additional phases.

The decomposer is skipped when deterministic playbook routes must stay atomic, when action items are plan-only with no actuator, or when policy fallback needs preserved replacement intents.

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
