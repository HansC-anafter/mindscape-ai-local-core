# Architecture

This section contains the currently released public architecture notes for Mindscape AI Local Core.

The listed pages have been checked against the current repository. Public architecture pages describe stable Local Core behavior first, then point to source landmarks or owner boundaries where useful.

## Recommended Reading Order

Start with the boundary documents, then read the runtime and execution documents that match your integration area.

### Overview and Boundaries

- [System Overview](./system-overview.md)
- [Local Boundary and External Interfaces](./local-boundary-and-external-interfaces.md)
- [Capability Hosting Boundary](./capability-hosting-boundary.md)
- [API Surface Boundaries](./api-surface-boundaries.md)

### Runtime and Execution

- [Runtime Environments and AOL Runtime](./runtime-environments.md)
- [Host Runtime, Resource Control, and Workspace UI Hosting](./host-runtime-resource-control.md)
- [Addressable Object Layer](./addressable-object-layer.md)
- [Execution Context and Prompt Assembly](./execution-context-and-prompt-assembly.md)
- [Meeting Orchestration](./meeting-orchestration.md)
- [TaskIR and Dispatch](./taskir-and-dispatch.md)

### Governance and Memory

- [Governance Context and Lens](./governance-context-and-lens.md)
- [Governed Memory Fabric](./governed-memory-fabric.md)

### Tools, Resources, and Code Navigation

- [Tool Retrieval and Resource Bindings](./tool-retrieval-and-resource-bindings.md)
- [Implementation Landmarks](./implementation-landmarks.md)

## Release Standards

Public architecture pages in this section use these standards:

- Lead with the user-visible or operator-visible Local Core behavior.
- Attach technical names after the behavior they support.
- Describe stable host contracts, adapter contracts, and repository landmarks.
- Summarize owner-specific capability or connector material by boundary responsibility.
- Include payload examples only when they are part of a released Local Core contract.
- Match the current repository structure before release.
