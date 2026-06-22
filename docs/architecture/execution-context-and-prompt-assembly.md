# Execution Context and Prompt Assembly

Mindscape AI Local Core uses execution context and prompt assembly to carry local runtime identity, workspace state, governance context, memory, tools, files, lens state, and meeting evidence into execution surfaces.

This page describes the released public architecture scope for the current repository.

## Context Carriers

Execution context is a set of scoped carriers used at different runtime boundaries.

The main carriers are:

- frontend execution context for actor, workspace, local mode, and local access state
- parameter adapter context for mapping local runtime values into tool and workflow parameters
- task execution metadata for playbook, trigger, progress, origin, actor, failure, and propagated tags
- meeting execution snapshots for runtime selection, access readiness, budget, retry posture, execution profile, and observability inputs
- executor selection context for workspace executor selection and binding state
- compatibility shims for callers that need adapter metadata

This split lets each boundary carry the context it needs.

## Meeting Execution Context

A meeting execution context is assembled at meeting start from workspace, runtime profile, local routing decisions, runtime environment, and runtime observability sources.

The meeting engine treats this context as a read-only runtime snapshot. It is used for budget headroom, retry posture, execution profile, local access readiness, and executor runtime awareness. TaskIR, meeting session metadata, governance context, and capability-owned state keep their separate responsibilities.

## Task Execution Context

Task execution context is stored as structured task metadata. It is built from playbook context, execution results, local domain context, and tags. The task context tracks the selected playbook, trigger source, current step, total steps, origin intent metadata, initiating actor, failure diagnostics, and default execution cluster.

This context is operational state for local task execution.

## Parameter Adaptation

Parameter adaptation uses an execution context data structure to map runtime fields into tool and workflow parameters. Stable local fields stay explicit, while adapter metadata can remain in additional context.

Validation and parameter transformation remain separate concerns. The context object is a carrier for execution inputs.

## Prompt Assembly

Prompt assembly in Local Core is runtime composition. The current implementation has two major assembly paths:

- workspace QA and planning context built by the conversation context builder
- meeting execution assembly text built by the meeting engine

The conversation context builder can assemble:

- governance-selected memory packet
- layered memory fallback from workspace core, project, and member memory
- workspace metadata
- active intents
- current tasks
- recent file analysis
- timeline and thread references
- conversation summary and recent messages
- semantic memory hits from vector search
- relevant tool context

The meeting assembly path can assemble:

- project context
- workspace asset map
- available tool inventory
- uploaded file references
- meeting session context, agenda, and user request
- active lens context
- active intents
- previous meeting decisions
- workflow evidence
- workspace context as reference material

These sections are context inputs. Role directives, adapter payloads, and assembly wording stay in owner-managed records until released as stable contracts.

## Tool Context

Tool context is discovered before assembly when possible. Meeting orchestration can pre-fetch relevant tools from agenda items and the user request. The assembly path then builds the tool inventory in this order:

- explicit workspace tool bindings, optionally ordered by matching RAG hits
- RAG-discovered tools when no explicit bindings exist
- installed manifest fallback as a last resort

Workspace QA context uses the same tool retrieval helper and can add explicitly bound workspace tools when semantic retrieval misses them.

Tool context is advisory input for planning and action extraction. Policy gates, dispatch gates, and executor availability still decide what can run.

## Memory and Governance Inputs

Context assembly prefers a governance-selected memory packet when available. If no governance packet is available, the QA path can fall back to layered workspace, project, and member memory. Semantic memory search can still contribute additional long-term memory hits.

This keeps memory context tied to governance and lens selection.

## Public Boundary

Local Core owns local context carriers, meeting execution snapshots, task execution context metadata, parameter adapter context, executor selection context, execution context assembly, tool context discovery, and governance-aware memory injection.

Related owners keep:

- assembly text or role instructions
- adapter request payloads
- external account lifecycle
- unrestricted raw memory export
- installed capability implementation internals
- old design-stage assembly compiler specifications

Public documentation describes stable context boundaries and assembly responsibilities. Assembly wording, migration notes, experimental compiler layers, and adapter payloads stay in owner-managed records.
