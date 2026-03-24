# Use Case: Portable Expert Viewpoint Modules / 可攜式專家視角模組

> **Category**: Cross-domain Cognitive Modules
> **Complexity**: High

---

## 1. Scenario Overview

**Goal**: Package a domain expert's way of seeing, judging, and executing work into a portable module that can be reused across workspaces, teams, or agent stacks.

**What is being packaged** is not a single prompt. In Mindscape, a portable expert viewpoint module is built from:

- a **viewpoint layer**: how to interpret a problem and what trade-offs to make
- a **role layer**: what kind of operator is acting and which tools or adjustments it uses
- a **workflow layer**: which steps, checks, and routines are available in the current scope
- a **continuity layer**: what should be remembered, revised, or written back over time

This is useful when you want AI to behave less like a generic assistant and more like a specific kind of expert with a repeatable working method.

---

## 2. Why Basic Prompt Reuse Breaks Down

Teams often try to "share expertise" by passing around:

- a long prompt
- a role description
- a workflow checklist

That usually fails over time because:

- the **viewpoint** is not separated from the task
- the **role configuration** is not persisted
- the **workflow** is not scoped to the right workspace or project
- there is no durable way to move the module between environments

Mindscape addresses this by separating those concerns into governed layers.

---

## 3. The Module Shape

### 3.1 Viewpoint Layer

`Mind-Lens` supplies the expert's viewpoint:

- what signals matter
- how to prioritize trade-offs
- what kind of tone or output texture should emerge

Examples:

- a brand lead lens emphasizes consistency, restraint, and channel coherence
- a research editor lens emphasizes evidence quality, source discipline, and uncertainty handling
- a narrative director lens emphasizes arc continuity, character intent, and performance cues

### 3.2 Role Layer

AI role configuration supplies:

- role name and identity
- associated playbooks
- allowed tools
- role-specific profile overrides

This is where a generic engine becomes a reusable operator such as:

- brand reviewer
- research editor
- narrative director

### 3.3 Workflow Layer

Playbooks provide the repeatable method:

- what steps to run
- what artifacts to produce
- what checks or approvals matter

Mindscape does not execute every playbook globally. It resolves the **effective playbooks** that are actually legal and applicable in the current workspace and project scope.

### 3.4 Portability Layer

A portable expert viewpoint module can move because the codebase already supports:

- portable configuration export
- AI role serialization inside portable export
- playbook scope and visibility rules
- lens preset packaging and installation

---

## 4. Three Example Viewpoints

### Brand Lead Viewpoint

**What it governs**:

- tone consistency
- review standards
- cross-channel alignment
- acceptable promotional trade-offs

**Why portability matters**:

- the same brand judgment can be reused across website, social, support, and campaign workflows
- local teams can adopt the same core viewpoint without rewriting brand prompts from scratch

### Research Editor Viewpoint

**What it governs**:

- evidence quality
- disagreement handling
- citation discipline
- long-form structure

**Why portability matters**:

- the same research method can travel between writing systems, research assistants, and knowledge workflows
- a team can share one evidence standard instead of re-teaching it in every prompt

### Narrative Direction Viewpoint

**What it governs**:

- role arcs
- performance intent
- storyline continuity
- output style for embodied or character-driven work

**Why portability matters**:

- the same narrative logic can persist across ideation, rehearsal, generation, and revision
- creator or character continuity can survive across sessions instead of resetting each run

---

## 5. How It Fits the Engine

Within Mindscape Engine, a portable expert viewpoint module plugs into the stack like this:

```text
Governance Context
  ├─ Mind-Lens
  ├─ Role configuration
  └─ Policy
        ↓
Meeting Runtime
        ↕
Governed Memory Fabric
        ↓
Scoped Playbooks / Tools / External Runtimes
```

This means the module influences:

- how work is framed
- how deliberation converges
- which workflows are in scope
- what gets written back and remembered

---

## 6. Product Interpretation

From a product perspective, this unlocks a useful middle ground:

- more structured than a prompt library
- more portable than a workspace-specific setup
- more opinionated than a generic agent framework

That makes Mindscape suitable for products that want to distribute:

- branded operating methods
- professional editorial standards
- domain-specific coaching styles
- narrative and creative direction systems

without collapsing those into a single assistant persona.

---

## 7. Related Architecture

- [Mind Lens](../core-architecture/mind-lens.md)
- [Governed Memory Fabric](../core-architecture/governed-memory-fabric.md)
- [System Overview](../core-architecture/system-overview.md)
- [Glossary](../getting-started/glossary.md)
