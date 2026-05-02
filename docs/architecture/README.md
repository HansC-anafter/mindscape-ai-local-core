# Architecture

This section contains the currently released public architecture notes for Mindscape AI Local Core.

Only documents that have been checked against the current repository are listed here. Unreleased API references, private validation material, legacy implementation notes, and internal authoring guides remain withheld until they are rewritten for public use.

## Recommended Reading Order

Start with the boundary documents, then read the runtime and execution documents that match your integration area.

### Overview and Boundaries

- [System Overview](./system-overview.md)
- [Local and Cloud Boundary](./local-cloud-boundary.md)
- [Capability Hosting Boundary](./capability-hosting-boundary.md)
- [API Surface Boundaries](./api-surface-boundaries.md)

### Runtime and Execution

- [Runtime Environments and AOL Runtime](./runtime-environments.md)
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

## Release Rules

Public architecture pages in this section must:

- describe stable architecture boundaries, not internal task history
- avoid work logs, open task markers, phase checklists, and dated closure claims
- avoid provider-specific payload details unless they are part of a stable public contract
- document capability hosting boundaries, not individual capability service implementations
- treat ignored, Docker-ignored, and CI-protected implementation paths as withheld by default
- match the current repository structure before release
