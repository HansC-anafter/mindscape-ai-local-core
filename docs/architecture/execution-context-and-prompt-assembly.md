# Execution Context and Prompt Assembly

Mindscape AI Local Core uses execution context and prompt assembly to carry local runtime identity, workspace state, governance context, memory, tools, files, lens state, and meeting evidence into execution surfaces.

This page describes the released public architecture scope for the current repository.

## Context Carriers

Execution context is not a single global object in the current Local Core implementation. It is a set of scoped carriers used at different runtime boundaries.

The main carriers are:

- frontend execution context for actor ID, workspace ID, local or external mode tags, and optional API authentication
- parameter adapter context for workspace, profile, project, execution, tenant, actor, subject user, and additional runtime values
- task execution context dictionaries for playbook code, trigger source, step progress, origin intent, initiating actor, failure state, default cluster, and propagated tags
- meeting execution context snapshots for executor runtime, runtime authentication state, budgets, retry policy, route kind, execution profile, and runtime observability
- executor route context for workspace executor selection and binding snapshots
- local compatibility shims for code that expects a cloud-style execution context contract

This split keeps Local Core from pretending that every caller uses the same context shape. Each boundary carries only the context it needs.

## Meeting Execution Context

A meeting execution context is assembled at meeting start from workspace, runtime profile, route decision, runtime environment, and runtime observability sources.

The meeting engine treats this context as a read-only runtime snapshot. It is used for budget headroom, retry behavior, route kind, execution profile, authentication status, and executor runtime awareness. It does not replace TaskIR, meeting session metadata, governance context, or capability-owned state.

## Task Execution Context

Task execution context is stored as structured task metadata. It is built from playbook context, execution results, local domain context, and tags. The task context tracks the selected playbook, trigger source, current step, total steps, origin intent metadata, initiating actor, failure diagnostics, and default execution cluster.

This context is operational state for local task execution. It should not be documented as a public user profile model or as an external tenant contract.

## Parameter Adaptation

Parameter adaptation uses an execution context data structure to map runtime fields into tool and workflow parameters. Known fields include workspace, profile, project, execution, tenant, actor, and subject user identifiers. Unknown fields remain in additional context so adapters can preserve caller-specific values without forcing them into core models.

Validation and parameter transformation remain separate concerns. The context object is a carrier, not a policy engine.

## Prompt Assembly

Prompt assembly in Local Core is runtime composition, not a public prompt template specification. The current implementation has two major assembly paths:

- workspace QA and planning context built by the conversation context builder
- meeting deliberation prompts built by the meeting engine prompt layer

The conversation context builder can assemble:

- governance-selected memory packet
- layered memory fallback from workspace core, project, and member memory
- workspace metadata
- active intents
- current tasks
- recent file analysis
- timeline and thread references
- conversation summary and recent messages
- side-chain context when policy allows it
- semantic memory hits from vector search
- relevant tool context

The meeting prompt layer can assemble:

- locale directive
- project context
- workspace asset map
- available tool inventory
- uploaded file references
- meeting session identity, workspace ID, project ID, round, agenda, and user request
- active lens context
- active intents
- previous meeting decisions
- workflow evidence
- workspace context as reference material

These sections are context inputs. They do not publish private role directives, provider payloads, or internal prompt text as a stable public contract.

## Tool Context

Tool context is discovered before prompt assembly when possible. Meeting orchestration can pre-fetch relevant tools from agenda items and the user request. The prompt layer then builds the tool inventory in this order:

- explicit workspace tool bindings, optionally ordered by matching RAG hits
- RAG-discovered tools when no explicit bindings exist
- installed manifest fallback as a last resort

Workspace QA context uses the same tool retrieval helper and can add explicitly bound workspace tools that were not found by semantic retrieval.

Tool context is advisory input for planning and action extraction. Policy gates, dispatch gates, and executor availability still decide what can run.

## Memory and Governance Inputs

Context assembly prefers a governance-selected memory packet when available. If no governance packet is available, the QA path can fall back to layered workspace, project, and member memory. Semantic memory search can still contribute additional long-term memory hits.

This keeps memory context tied to governance and lens selection instead of treating prompt assembly as unrestricted retrieval.

## Public Boundary

Local Core owns local context carriers, meeting execution snapshots, task execution context metadata, parameter adapter context, executor route context, prompt context assembly, tool context discovery, and governance-aware memory injection.

Local Core does not publicly own:

- private prompt text or role instructions
- provider-native request payloads
- external tenant lifecycle
- unrestricted raw memory export
- installed capability implementation internals
- old design-stage prompt compiler specifications

Public documentation should describe stable context boundaries and assembly responsibilities. Internal prompt wording, migration notes, experimental compiler layers, and provider-specific payloads remain withheld.
