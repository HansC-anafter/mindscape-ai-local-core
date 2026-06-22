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

These layers are related and distinct. Public docs preserve their separate roles so memory remains reviewable.

## Canonical Memory Contract

The canonical memory contract includes memory items, versions, evidence links, memory edges, and writeback runs. Memory items carry reviewable claim, lifecycle, evidence, and source metadata through stable public fields.

Memory versions preserve claim snapshots. Evidence links connect memory items to source artifacts such as session digests, reasoning traces, lens receipts, meeting decisions, task executions, artifact results, and writeback receipts.

The public contract is evidence-oriented: memory should be traceable to the run or artifact that produced it.

## Meeting Writeback

Meeting close writeback creates a reviewable canonical memory trail from meeting outputs and evidence. It records durable memory, versions it, links it to evidence, and updates compatibility projections for existing workspace, project, and member memory consumers.

The writeback path can attach additional execution and governance evidence when available. This lets Local Core connect deliberation, execution, artifacts, and governance into one reviewable memory chain through stable memory records.

## Governance Memory Packets

Governance services select and compile compact memory packets for execution context. The selector combines governed workspace, project, member, goal, episodic, and knowledge surfaces according to workspace mode and policy context.

The packet compiler turns the selected packet into ordered context sections. Semantic memory can contribute when enabled, but route planning details remain internal.

Workspace governance surfaces provide review, lifecycle, health, and impact views for governed memory.

## Semantic Memory and Retrieval

The repository includes pgvector-backed semantic support:

- pgvector-backed vector database configuration and health checks
- pgvector extension support when the configured PostgreSQL server is available
- semantic search services for memory embeddings, playbook knowledge, personal context, and external documents
- tool and playbook embedding support for retrieval

The semantic service layer and pgvector-backed retrieval path are present in the repository. Public documentation describes semantic memory as implemented service support. Individual vector helpers become public routes when released as stable contracts.

## World Memory

World memory is implemented separately from semantic vector search. The world memory core provides normalized world-state snapshots, bounded world memory packets, and world card projections.

World memory normalizes governed context into bounded packets. The projection compiler turns those packets into concise world cards for bounded context injection.

World memory is bounded world-state continuity. Canonical memory, semantic retrieval, and adapter payload handling keep their own responsibilities.

## Public Boundary

Local Core owns governed memory contracts, writeback orchestration, evidence linking, memory selection, semantic retrieval services, and world memory projection utilities.

Related owners keep:

- adapter payload dumps
- unreviewed promotion of transient context into durable memory
- receipt internals
- account-level memory maintained by surrounding systems
- capability-specific memory schemas during owner-specific lifecycle

Public memory documentation preserves the distinction between canonical memory, semantic retrieval, and world memory. Task logs, migration checklists, verification captures, and draft data dumps stay in owner-managed records.
