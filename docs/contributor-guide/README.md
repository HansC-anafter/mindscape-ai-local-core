# Contributor Guide

This directory contains guides for external contributors who want to extend Mindscape with their own tools, playbooks, and packs.

## Start Here

### [Adapter Compilation Guide (ABI)](./adapter-compilation-guide.md)

**The definitive guide for integrating external tools into Mindscape.**

This guide provides the **Application Binary Interface (ABI)** that enables you to:
- Wrap your tools as Mindscape-compatible adapters (CLI/HTTP/MCP)
- Create tool manifests with governance fields
- Build playbooks that orchestrate multiple tools
- Publish packs to community or official registries

**What You'll Learn**:
- **3 Deliverables + 1 Validation**: Tool Adapter, Tool Manifest, Playbook, Validation
- **Three Adapter Levels**: L0 (CLI), L1 (HTTP), L2 (MCP)
- **Governance Fields**: Side effects, risk levels, confirmation requirements
- **Pack Publishing**: Community (public) vs Official (private) registries
- **IDE LLM Templates**: Ready-to-use prompts for tool wrapping and playbook creation

**Target Audience**:
- External developers building tools for Mindscape
- Contributors creating playbooks and packs
- Anyone wanting to integrate existing tools into Mindscape workflows

---

## Quick Links

- [Adapter Compilation Guide (ABI)](./adapter-compilation-guide.md) - Complete integration guide
- [Playbook Development Guide](../playbook-development/getting-started.md) - Playbook creation details
- [Core Architecture](../core-architecture/README.md) - System architecture overview

---

## The Mindscape Value Proposition

> **Mindscape doesn't compete in the tool market; we provide *Tool ABI + Pack Registry + Playbook Runtime*, enabling every tool you build to be governed, orchestrated, and collaboratively replayed.**

### What Mindscape Provides

- **Tool ABI**: Three adapter levels (CLI/HTTP/MCP) for tool integration
- **Pack Registry**: Public (community) and private (official) distribution
- **Playbook Runtime**: Orchestration, governance, and traceability

### What You Deliver

1. **Tool Adapter** (L0/L1/L2) - Wrap your tool
2. **Tool Manifest** (with governance) - Enable governance and discovery
3. **Playbook** (Markdown + YAML) - Orchestrate tools into workflows
4. **Validation** (schema, compatibility) - Ensure correctness

### Result

Every tool you build can be **governed, orchestrated, and collaboratively replayed** within Mindscape.

---

## Workflow: From Tool to Pack

```
Your Tool
    ↓
[Adapter Compilation Guide]
    ↓
Tool Adapter (L0/L1/L2)
    ↓
Tool Manifest (with governance)
    ↓
Playbook (orchestration)
    ↓
Pack (distribution)
    ↓
Registry (community or official)
    ↓
Users Install & Run
```

---

## Support

- **Questions**: Open a discussion in `mindscape-ai-local-core`
- **Issues**: Report bugs or request features
- **Contributions**: Submit PRs to improve guides







