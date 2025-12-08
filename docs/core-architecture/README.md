# Core Architecture

This directory contains the core architecture documentation for Mindscape AI.

## Directory Structure

### [Sandbox System](./sandbox/)
System-level Sandbox architecture, unifying all AI write operations.

- [Sandbox System Architecture](./sandbox/sandbox-system-architecture.md)
- [Sandbox System Implementation Steps](./sandbox/sandbox-system-implementation-steps.md)
- [Sandbox System Summary](./sandbox/sandbox-system-summary.md)

### [Project + Flow](./project-flow/)
Project and Playbook Flow architecture for multi-playbook collaboration.

- [Project + Flow Architecture](./project-flow/project-flow-architecture.md)
- [Project + Flow Implementation Steps](./project-flow/project-flow-implementation-steps.md)
- [Project + Flow Summary](./project-flow/project-flow-summary.md)

### [Three.js Sandbox](./threejs/)
Three.js Hero scene Sandbox implementation planning and examples.

- [Three.js Sandbox Index](./threejs/threejs-sandbox-index.md)
- [Three.js Sandbox Implementation Plan](./threejs/threejs-sandbox-implementation-plan.md)
- [Three.js Sandbox Implementation Steps](./threejs/threejs-sandbox-implementation-steps.md)
- [Three.js Sandbox Code Examples](./threejs/threejs-sandbox-code-examples.md)
- [Three.js Sandbox Quick Start](./threejs/threejs-sandbox-quick-start.md)
- [Three.js Sandbox Summary](./threejs/threejs-sandbox-summary.md)

## Core Concepts

### Project + Flow + Sandbox Architecture

**Project**: Deliverable-level container with its own lifecycle (open, closed, archived)

**Sandbox**: Unified file space shared across all playbooks in a project

**Playbook Flow**: Multi-playbook orchestration with dependency resolution

**Value**:
- Unified worldview (same files/specs)
- Execution order enforcement
- Deliverable-level container

## Reading Guide

### Quick Overview
1. [Sandbox System Summary](./sandbox/sandbox-system-summary.md)
2. [Project + Flow Summary](./project-flow/project-flow-summary.md)

### Deep Dive
1. [Sandbox System Architecture](./sandbox/sandbox-system-architecture.md)
2. [Project + Flow Architecture](./project-flow/project-flow-architecture.md)

### Getting Started
1. [Sandbox System Implementation Steps](./sandbox/sandbox-system-implementation-steps.md)
2. [Project + Flow Implementation Steps](./project-flow/project-flow-implementation-steps.md)
3. [Three.js Sandbox Quick Start](./threejs/threejs-sandbox-quick-start.md)

## Architecture Relationship

```
Workspace (long-term room, years of collaboration)
    ↓
Project (deliverable container, has its own lifecycle)
    ↓
Playbook Flow (execution flow)
    ↓
Shared Sandbox (file world)
    ↓
SandboxManager (system-level)
```

---