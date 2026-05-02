# Governed Memory Fabric

Mindscape AI Local Core uses governed memory to preserve continuity, evidence, and reviewable state across local workspace work. This page describes the released public architecture scope for the current repository.

## Memory Layers

Local Core contains several memory layers that serve different continuity needs:

- workspace core memory for durable workspace identity, style constraints, milestones, learnings, and projected episodes
- project memory for project decisions, version evolution, artifact index entries, projected episodes, and key conversations
- member profile memory for skills, preferences, project experience, projected episodes, and repeated learnings
- canonical memory items for governed episodic, process, interface, core, and procedural memory
- semantic memory and retrieval support through pgvector-backed services
- world memory packets for bounded world-state continuity

These layers are related but not interchangeable. Public docs should not flatten them into a single ungoverned memory bucket.

## Canonical Memory Contract

The canonical memory contract includes memory items, versions, evidence links, memory edges, and writeback runs. Memory items carry kind, layer, lifecycle status, verification status, salience, confidence, subject, context, claim, summary, and source pipeline metadata.

Memory versions preserve claim snapshots. Evidence links connect memory items to source artifacts such as session digests, reasoning traces, lens receipts, meeting decisions, task executions, artifact results, and writeback receipts.

The public contract is evidence-oriented: memory should be traceable to the run or artifact that produced it.

## Meeting Writeback

Meeting close writeback creates or reuses a writeback run, compiles a session digest, creates a canonical memory item, creates an initial version, attaches evidence, and dispatches legacy projection adapters for existing workspace, project, and member memory consumers.

The writeback orchestrator also collects additional evidence from stage results, execution traces, intent logs, governance decisions, and lens patches. This lets Local Core connect deliberation, execution, artifacts, and governance into one reviewable memory chain.

## Governance Memory Packets

Governance services select and compile compact memory packets for execution context. The selector combines core memory, verified knowledge, candidate knowledge, active goals, pending goals, episodic memory, project memory, and member memory according to workspace mode and policy context.

The packet compiler turns the selected packet into ordered prompt sections. The route plan can include core directives, verified knowledge, goals, project memory, member memory, episodic evidence, and semantic hits when enabled.

Workspace governance routes expose canonical memory listing, memory detail, lifecycle transitions, memory health, and memory impact graph views. These routes are review surfaces for governed memory, not unrestricted write endpoints.

## Semantic Memory and Retrieval

The repository includes pgvector-backed semantic support:

- vector database configuration and connection testing through the vector database route
- pgvector extension creation during startup when the configured PostgreSQL server is available
- semantic search services for memory embeddings, playbook knowledge, personal context, and external documents
- tool embedding services for RAG-based tool and playbook discovery
- startup warm-up that refreshes the tool RAG corpus and records capability embedding coverage

Some generic vector search API routes remain adapter-gated, but the semantic service layer and pgvector-backed retrieval path are present in the repository. Public documentation should describe semantic memory as implemented service support with adapter-dependent public route coverage.

## World Memory

World memory is implemented separately from semantic vector search. The world memory core provides normalized world-state snapshots, bounded world memory packets, and world card projections.

The world state adapter normalizes governed sidecar context such as schedule projections and performance context into a bounded packet. The projection compiler turns that packet into a concise world card for prompt-safe context injection.

World memory should be described as bounded world-state continuity. It is not a replacement for canonical memory, semantic retrieval, or raw provider payload storage.

## Public Boundary

Local Core owns governed memory contracts, writeback orchestration, evidence linking, memory selection, semantic retrieval services, and world memory projection utilities.

Local Core does not publicly own:

- provider-native payload dumps as canonical memory
- unreviewed promotion of transient context into durable memory
- private receipt internals as public APIs
- cloud account or tenant memory as Local Core ownership
- capability-specific memory schemas unless promoted into a stable Local Core contract

Public memory documentation should preserve the distinction between canonical memory, semantic retrieval, and world memory. It should not publish internal task logs, migration checklists, private validation material, or unreleased data dumps.
