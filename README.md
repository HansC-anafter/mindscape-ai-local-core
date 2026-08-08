# Mindscape AI Local Core

Mindscape AI Local Core is the open-source local runtime host for governed AI work.

It provides the local workspace engine, governance context, meeting orchestration, governed memory, TaskIR dispatch, tool retrieval, resource binding, optional connector boundaries, and the Addressable Object Layer runtime surface used by the local application.

## Public Scope

This repository documents the Local Core boundary only:

- Local workspace runtime and Docker Compose startup.
- Governance context, lens composition, and policy surfaces.
- Meeting orchestration and TaskIR dispatch.
- Governed memory, including canonical memory, semantic retrieval, and world-memory surfaces.
- Addressable Object Layer runtime ownership and resource identity.
- Host runtime sessions, local resource lanes, queue visibility, and workspace capacity controls.
- Tool retrieval, resource binding, and API surface boundaries.
- External integration boundaries at the contract level.

The public documentation focuses on stable Local Core contracts: local runtime behavior, repository-backed architecture landmarks, host interfaces, integration boundaries, and setup paths. Owner-specific service material, generated runtime evidence, protected implementation paths, and operational records stay with their owning project records until they become stable public Local Core contracts.

## Start Locally

```bash
git clone https://github.com/HansC-anafter/mindscape-ai-local-core.git
cd mindscape-ai-local-core
./scripts/start.sh
```

On Windows PowerShell, run `.\scripts\start.ps1`. These canonical launchers create machine-owned internal runtime secrets automatically; users only configure optional provider keys and other product settings.

The local web console is served by the Compose stack. For setup details and platform notes, use the retained public setup path:

- [Getting Started](docs/getting-started/README.md)
- [Docker Setup](docs/getting-started/docker.md)
- [Manual Installation](docs/getting-started/installation.md)
- [Platform Notes](docs/getting-started/platform-specific.md)
- [Troubleshooting](docs/getting-started/troubleshooting.md)

## Architecture

The released public architecture set is intentionally small and checked against the current repository shape:

- [System Overview](docs/architecture/system-overview.md)
- [Local Boundary and External Interfaces](docs/architecture/local-boundary-and-external-interfaces.md)
- [Runtime Environments](docs/architecture/runtime-environments.md)
- [Host Runtime, Resource Control, and Workspace UI Hosting](docs/architecture/host-runtime-resource-control.md)
- [Addressable Object Layer](docs/architecture/addressable-object-layer.md)
- [Governed Memory Fabric](docs/architecture/governed-memory-fabric.md)
- [Governance Context and Lens](docs/architecture/governance-context-and-lens.md)
- [Execution Context and Prompt Assembly](docs/architecture/execution-context-and-prompt-assembly.md)
- [Meeting Orchestration](docs/architecture/meeting-orchestration.md)
- [TaskIR and Dispatch](docs/architecture/taskir-and-dispatch.md)
- [Tool Retrieval and Resource Bindings](docs/architecture/tool-retrieval-and-resource-bindings.md)
- [Capability Hosting Boundary](docs/architecture/capability-hosting-boundary.md)
- [API Surface Boundaries](docs/architecture/api-surface-boundaries.md)

The public documentation entry is [docs/README.md](docs/README.md).

## Boundary Summary

Local Core owns the local runtime host, local workspace state, governed context assembly, memory serving surfaces, meeting-to-dispatch handoff, local tool retrieval, object/resource identity, host runtime session state, local resource capacity control, workspace-hosted capability shells, and public boundary contracts.

Related systems own account administration, managed service operations, capability implementation details, release operations, and generated operational evidence. Local Core integrates with those systems through explicit host and adapter contracts.

## License

See the repository license file for project licensing terms.
