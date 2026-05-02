# Architecture

This section contains the currently released public architecture notes for Mindscape AI Local Core.

Only documents that have been checked against the current repository are listed here. Unreleased API references, private validation material, legacy implementation notes, and internal authoring guides remain withheld until they are rewritten for public use.

## Released Documents

- [System Overview](./system-overview.md)
- [Local and Cloud Boundary](./local-cloud-boundary.md)
- [Runtime Environments and AOL Runtime](./runtime-environments.md)
- [Capability Hosting Boundary](./capability-hosting-boundary.md)
- [API Surface Boundaries](./api-surface-boundaries.md)
- [Addressable Object Layer](./addressable-object-layer.md)
- [Governed Memory Fabric](./governed-memory-fabric.md)
- [Governance Context and Lens](./governance-context-and-lens.md)
- [Execution Context and Prompt Assembly](./execution-context-and-prompt-assembly.md)
- [Tool Retrieval and Resource Bindings](./tool-retrieval-and-resource-bindings.md)
- [Meeting Orchestration](./meeting-orchestration.md)
- [TaskIR and Dispatch](./taskir-and-dispatch.md)
- [Implementation Landmarks](./implementation-landmarks.md)

## Release Rules

Public architecture pages in this section must:

- describe stable architecture boundaries, not internal task history
- avoid work logs, open task markers, phase checklists, and dated closure claims
- avoid provider-specific payload details unless they are part of a stable public contract
- document capability hosting boundaries, not individual capability service implementations
- treat ignored, Docker-ignored, and CI-protected implementation paths as withheld by default
- match the current repository structure before release
