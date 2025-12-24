# Execution Context Four-Layer Model

> **Note**: This document describes a **conceptual mapping**, not a structural change. The four-layer model maps existing fields and concepts, without introducing new APIs or models.

**Last updated**: 2025-12-22

---

## Overview

The Execution Context four-layer model provides a conceptual framework for understanding how different aspects of execution context are organized. It separates "what to do" (Task/Goal) from "how to do it" (Lens/Perspective), "what cannot be done" (Policy/Constraints) from "what materials to use" (Assets/Memory).

## Core Concept

**Key Insight**: "What to do / what to achieve" (boundaries, requirements, specifications) and **"how to do it / from whose perspective / in what way"** (viewpoint, attention allocation, tone and value trade-offs) are fundamentally different dimensions.

The four layers are:

1. **Task / Goal** (What to do)
2. **Policy / Constraints** (What cannot be done, what must be complied with)
3. **Lens / Perspective** (How to do it, where to focus attention)
4. **Assets / Memory** (What materials to use)

**Core Principle**: **Task remains unchanged, Lens can be swapped; Policy is fixed to maintain bottom line; Assets provide materials.**

---

## Four-Layer Model Definition

### A. Task / Goal (What to do)

**Purpose**: Task boundaries, input/output specifications, acceptance criteria, delivery format.

**Examples**:
- Write product concept introduction copy
- Create landing page
- Write shooting script

**Characteristics**:
- Defines "what to do"
- Specifies input/output format
- Defines acceptance criteria
- Specifies delivery format

**Field Mapping**:
- `playbook_id`: Task definition (Playbook)
- `task_id`: Task instance ID
- `ExecutionPlan.goal`: Goal description
- `ExecutionPlan.input_spec`: Input specification
- `ExecutionPlan.output_spec`: Output specification
- `ExecutionPlan.acceptance_criteria`: Acceptance criteria
- `tags["delivery_format"]`: Delivery format (optional metadata)

**Code References**:
- `backend/app/models/playbook.py` - Playbook model
- `backend/app/core/execution_context.py` - ExecutionContext model

---

### B. Policy / Constraints (What cannot be done, what must be complied with)

**Purpose**: Constraints and consistency rules (guardrails).

**Examples**:
- Brand forbidden words
- Legal compliance
- CTA cannot be exaggerated
- Color/font specifications

**Characteristics**:
- Defines constraints and consistency
- Acts as guardrails, limiting expression scope
- Different from Lens: Policy defines "what cannot be done", Lens defines "how to do it"

**Field Mapping**:
- `SideEffectLevel`: Side effect level (READONLY/SOFT_WRITE/EXTERNAL_WRITE)
- `requires_approval`: Whether approval is required
- `governance/approval` flow: Approval workflow
- `tags["policy_set_id"]`: Policy set ID (optional metadata)
- `tags["constraints"]`: Constraint list (optional metadata)
- `workspace.metadata`: Workspace-level policy settings

**Code References**:
- `backend/app/models/surface.py:62` - `Command.requires_approval`
- `backend/app/core/execution_context.py:25` - `ExecutionContext.tags`

---

### C. Lens / Perspective (How to do it)

**Purpose**: Attention allocation, trade-offs, narrative path (viewpoint, driving style).

**Examples**:
- Designer's visual framing habits
- Voice actor's rhythm and emotional curve
- Writer's syntax and metaphor preferences
- Director's camera language
- Screenwriter's value stance

**Characteristics**:
- Defines where to focus attention, how to make trade-offs, what narrative path to use
- This is the core of Mind Lens
- Can be stacked, weighted, scoped
- Replaceable and versionable

**Field Mapping**:
- `ExecutionContext.mind_lens`: Resolved Mind Lens for role-based perspective
- `LensComposition.lens_stack`: Lens stack in composition
- `tags["lens_stack"]`: Lens stack metadata (optional)
- `MindLensInstance`: Personal/author-level lens instance
- `LensComposition`: Multi-lens combination recipe

**Code References**:
- `backend/app/models/mind_lens.py` - Mind Lens core models
- `backend/app/models/lens_composition.py` - Lens Composition model
- `backend/app/core/execution_context.py:26` - `ExecutionContext.mind_lens`

---

### D. Assets / Memory (What materials to use)

**Purpose**: Data materials, not perspective, but will be interpreted by lens.

**Examples**:
- Workspace metadata (brand, voice, constraints)
- Data sources (files, APIs, databases)
- Artifact references (previous outputs)
- Project memory (decisions, version evolution)

**Characteristics**:
- Provides materials for execution
- Not a perspective, but raw data
- Will be interpreted by lens
- Can be referenced and reused

**Field Mapping**:
- `workspace.metadata`: Workspace metadata
- `data_sources`: Data source references
- `artifact_refs`: Artifact references
- `tags["assets_refs"]`: Asset references (optional metadata)
- Project memory: Decision history and context

**Code References**:
- `backend/app/models/workspace.py` - Workspace model
- `backend/app/core/execution_context.py:25` - `ExecutionContext.tags`

---

## Layer Separation Principles

### 1. Task Independence

- Task definition is independent of Lens
- Same task can be executed with different lenses
- Task specifies "what", not "how"

### 2. Policy as Guardrails

- Policy defines constraints, not perspective
- Policy is fixed to maintain bottom line
- Policy acts as guardrails, limiting expression scope

### 3. Lens as Replaceable Viewpoint

- Lens defines "how to interpret", not "what cannot be done"
- Lens can be stacked, weighted, scoped
- Lens is replaceable and versionable
- Same task + different lens = different results

### 4. Assets as Materials

- Assets provide materials, not perspective
- Assets will be interpreted by lens
- Assets can be referenced and reused

---

## Usage Examples

### Example 1: Task with Different Lenses

```python
# Same task: "Write product introduction"
task = {
    "playbook_id": "content_drafting",
    "goal": "Write product introduction",
    "input_spec": {"product_name": "Mindscape AI"},
    "output_spec": {"format": "markdown", "length": "500-800 words"}
}

# Different lenses produce different results
lens_writer = {"role": "writer", "style": "journalistic"}
lens_marketer = {"role": "marketer", "style": "persuasive"}
lens_technical = {"role": "writer", "style": "technical"}

# Same task + different lens = different output style
```

### Example 2: Policy Constraints

```python
# Policy defines constraints
policy = {
    "forbidden_words": ["guarantee", "best", "perfect"],
    "compliance": "legal_review_required",
    "brand_guidelines": "follow_brand_style_guide"
}

# Policy acts as guardrails
# Even with different lenses, policy constraints must be followed
```

### Example 3: Lens Composition

```python
# Multiple lenses can be composed
composition = LensComposition(
    composition_id="composite_001",
    lens_stack=[
        LensReference(lens_instance_id="writer_001", weight=0.6),
        LensReference(lens_instance_id="designer_001", weight=0.4)
    ],
    fusion_strategy="priority_then_weighted"
)

# Fused lens context is applied to execution
fused_context = fuse_composition(composition)
```

### Example 4: Assets Reference

```python
# Assets provide materials
assets = {
    "data_sources": ["product_spec.md", "market_research.pdf"],
    "artifact_refs": ["previous_draft_v1.md"],
    "workspace_metadata": {"brand_voice": "professional", "tone": "friendly"}
}

# Assets are interpreted by lens
# Same assets + different lens = different interpretation
```

---

## Implementation Notes

### Conceptual Mapping, Not Structural Change

- The four-layer model is a **conceptual mapping**, not a new API
- Existing fields are preserved and used as-is
- New information can be added via `tags/metadata` as optional keys
- Maintains backward compatibility

### Field Usage

- Use existing `ExecutionContext`, `playbook`, `mind_lens`, `workspace` fields
- Four layers are conceptual overlays, not structural changes
- Use `tags/metadata` for incremental extension
- Maintain backward compatibility

### Best Practices

1. **Keep Task Independent**: Task definition should not depend on Lens
2. **Enforce Policy**: Policy constraints must be enforced regardless of Lens
3. **Compose Lenses**: Use Lens Composition for multi-lens scenarios
4. **Reference Assets**: Reference assets through workspace metadata and tags

---

## Related Documentation

- [Execution Context](./execution-context.md) - Core ExecutionContext abstraction
- [Mind Lens](./mind-lens.md) - Mind Lens core architecture (planned)
- [Lens Composition](./lens-composition.md) - Lens Composition architecture (planned)
- [System Overview](./system-overview.md) - Complete system architecture

---

**Last updated**: 2025-12-22


