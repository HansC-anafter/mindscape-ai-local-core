# Quick Start Guide

Mindscape AI Local Core can be approached in two fast paths:

1. **Demo-first** — see what the repo can demonstrate today
2. **Engine-first** — understand the architecture before touching any runtime lane

## Before You Start

Make sure you have:

1. Installed Mindscape AI Local Core (see [Installation Guide](./installation.md))
2. Configured at least one LLM API key if you want live meeting/runtime behavior
3. Started the backend server
4. Optionally started the frontend if you want the full workspace UI

Default local URLs:

- **Frontend**: `http://localhost:3001` (Docker) or `http://localhost:3000` (manual install)
- **API Docs**: `http://localhost:8000/docs`

## Path A: Demo-First

If you want the shortest path to "what can this repo show me today?", read these in order:

1. [Demo Gallery](../demo-gallery/README.md)
2. [Single-Image Preview Mesh](../use-cases/single-image-preview-mesh.md)
3. [Complex Relation Stress Preview Mesh](../use-cases/complex-relation-stress-preview-mesh.md)
4. [Candidate vs Fallback Comparison](../use-cases/candidate-vs-fallback-comparison.md)
5. [Fixed-Scene Subject Swap](../use-cases/fixed-scene-subject-swap.md)
6. [Artifact Taxonomy](../reference/artifact-taxonomy.md)

What you will learn:

- which outputs are `preview`, `candidate`, or `fallback`
- which artifacts are public-safe to talk about
- which demos are scene/subject continuity stories rather than pack implementation stories

Current checked-in evidence:

- the `Single-Image Preview Mesh` lane now includes a source image, a captured preview render, and a machine-readable smoke summary
- the `Complex Relation Stress Preview Mesh` lane now adds a public-safe honesty case for a denser indoor image, with front/oblique/side stills checked in

Important:

- some demo lanes depend on installable capability/runtime packs from `mindscape-ai-cloud`
- local-core remains the governance host and bounded writeback layer

## Path B: Engine-First

If you want the architecture before the demos, read these in order:

1. [System Overview](../core-architecture/system-overview.md)
2. [Spatial Runtime Planning](../core-architecture/spatial-runtime-planning.md)
3. [Governed Memory Fabric](../core-architecture/governed-memory-fabric.md)
4. [Mind Meeting — Five-Layer Architecture](../core-architecture/meeting-engine-dispatch.md)

What you will learn:

- how governance context, meeting runtime, and memory fit together
- why `TaskIR` and `SpatialSchedulingIR` are different artifacts
- where consumer runtimes stop and local-core ownership begins

## Create a Workspace

When you want to explore the host runtime directly:

1. Open the web interface
2. Create a workspace, or call the API:

```bash
curl -X POST "http://localhost:8000/api/v1/workspaces" \
  -H "Content-Type: application/json" \
  -d '{"name": "My First Workspace"}'
```

3. Start a conversation in the workspace
4. Use that workspace as the host for playbooks, installed runtime packs, and future writeback

## Core Terms To Know

- **Workspace** — the governed host container for conversations, artifacts, and continuity
- **Meeting Runtime** — the live deliberation layer
- **TaskIR** — the bounded control artifact for execution-ready work
- **SpatialSchedulingIR** — the bounded planning artifact for spatial/world execution intent
- **World Summary / Writeback** — the bounded continuity record written back after execution

## Next Steps

- If you want scenario examples, go to [Use Case Gallery](../use-cases/README.md)
- If you want the public-safe artifact names, go to [Artifact Taxonomy](../reference/artifact-taxonomy.md)
- If you want the local/cloud split, read [Local/Cloud Boundary](../core-architecture/local-cloud-boundary.md)
