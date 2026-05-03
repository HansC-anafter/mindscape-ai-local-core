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
- Tool retrieval, resource binding, and API surface boundaries.
- Local-to-cloud boundaries at the contract level.

The public documentation does not publish cloud product internals, private service payloads, ignored or CI-protected implementation paths, capability service internals, provider-specific payloads, operational work logs, private validation material, or unreleased endpoint references.

## Start Locally

```bash
git clone https://github.com/HansC-anafter/mindscape-ai-local-core.git
cd mindscape-ai-local-core
docker compose up -d
```

The local web console is served by the Compose stack. For setup details and platform notes, use the retained public setup path:

- [Getting Started](docs/getting-started/README.md)
- [Docker Setup](docs/getting-started/docker.md)
- [Manual Installation](docs/getting-started/installation.md)
- [Platform Notes](docs/getting-started/platform-specific.md)
- [Troubleshooting](docs/getting-started/troubleshooting.md)

## Architecture

The released public architecture set is intentionally small and checked against the current repository shape:

- [System Overview](docs/architecture/system-overview.md)
- [Local and Cloud Boundary](docs/architecture/local-cloud-boundary.md)
- [Runtime Environments](docs/architecture/runtime-environments.md)
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

Local Core owns the local runtime host, local workspace state, governed context assembly, memory serving surfaces, meeting-to-dispatch handoff, local tool retrieval, object/resource identity, and public boundary contracts.

Local Core does not own cloud tenant orchestration, billing, provider control planes, managed remote execution services, capability-internal services, private release playbooks, or generated operational evidence.

## License

See the repository license file for project licensing terms.
