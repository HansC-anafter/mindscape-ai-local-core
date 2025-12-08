# Sandbox System Design Summary

## 🎯 Core Insights

### Key Principle

> **Whenever "AI helps you modify something" (not just reading), it should go through the sandbox layer.**

This is not just for three.js—it's a **unified abstraction for all AI write operations**.

## 🏗️ System Architecture

### Three-Layer Design

```
┌─────────────────────────────────────┐
│  UI Layer (Unified)                  │
│  - Sandbox Viewer (shared component) │
│  - Different type preview renderers  │
└─────────────────────────────────────┘
           ↓
┌─────────────────────────────────────┐
│  Tool Layer                          │
│  - sandbox.threejs.*                 │
│  - sandbox.writing.*                 │
│  - sandbox.project.*                 │
└─────────────────────────────────────┘
           ↓
┌─────────────────────────────────────┐
│  SandboxManager (System-Level)       │
│  - Unified version management        │
│  - Unified diff and summaries        │
│  - Unified storage abstraction       │
└─────────────────────────────────────┘
```

## 📦 Sandbox Types

### 1. Three.js Hero (`threejs_hero`)

**Features:**
- Visual + code hybrid
- Requires preview and visual selection
- Structure: `versions/v1/Component.tsx`, `index.html`

**Tools:**
- `sandbox.threejs.create_scene`
- `sandbox.threejs.read_scene`
- `sandbox.threejs.apply_patch`

### 2. Writing Project (`writing_project`)

**Features:**
- Pure text content
- Structured chapters
- Structure: `outline.md`, `ch01.md`, `ch02.md`, `meta.json`

**Tools:**
- `sandbox.writing.create_project`
- `sandbox.writing.create_chapter`
- `sandbox.writing.read_section`
- `sandbox.writing.apply_patch`

### 3. Project Repo (`project_repo`)

**Features:**
- Can be patch collections or dedicated git branch
- Requires merge mechanism
- Structure: `patches/`, `branch/`, or `sandbox/` directory

**Tools:**
- `sandbox.project.plan_patch`
- `sandbox.project.apply_patch`
- `sandbox.project.merge_to_main` (requires user confirmation)

## ✨ Unified Capabilities

### 1. Unified Version Management

All sandbox types share:
- Version format: v1, v2, v3...
- Version metadata format
- Version listing and switching

### 2. Unified Partial Modification

All sandbox types support:
- **Text files** → Select range as patch scope
- **Code** → `start_line / end_line` + diff
- **Three.js** → Visual selection + mapping to config

### 3. Unified Change Visualization

All sandbox types share:
- Version timeline
- Before/After comparison
- AI verbal summaries

**Example:**
```
Book draft v3: Added XX section, deleted YY paragraph
Three.js v2: Fewer particles, color changed to purple
Repo v5: Added two functions, deleted one unused import
```

## 🔄 Migration Strategy

### Current State → New Architecture

**Old Way:**
```python
await filesystem_write_file(
    file_path="artifacts/threejs_hero_landing/{execution_id}/Component.tsx",
    content=generated_code
)
```

**New Way:**
```python
sandbox_id = await sandbox.create_sandbox(
    sandbox_type="threejs_hero",
    context={"slug": "particle-network-001"},
    workspace_id=workspace_id
)

await sandbox.write_file(
    sandbox_id=sandbox_id,
    file_path="Component.tsx",
    content=generated_code
)
```

### Migration Priority

1. **Phase 1**: Implement system-level SandboxManager
2. **Phase 2**: Migrate `threejs_hero_landing` Playbook
3. **Phase 3**: Migrate `yearly_personal_book` Playbook
4. **Phase 4**: Migrate other related Playbooks

## 🎨 Unified UI Pattern

### Sandbox Viewer Shared Component

All sandbox types share the same UI structure:

```
┌─────────────────────────────────────┐
│  [Preview] [Source] [History] [Chat] │
├─────────────────────────────────────┤
│  Preview Area (rendered by sandbox_type) │
├─────────────────────────────────────┤
│  Version Timeline                    │
│  [v1] [v2] [v3] [v4]                │
│                                      │
│  Change Summary:                     │
│  ✅ Particle count reduced from 300 to 150 │
│  ✅ Line opacity slightly decreased  │
└─────────────────────────────────────┘
```

### Preview Renderer

Select corresponding renderer based on `sandbox_type`:
- `threejs_hero` → Three.js preview
- `writing_project` → Markdown renderer
- `project_repo` → Code diff

## 💡 Design Value

### 1. Clear Security Boundaries

- Seeing `sandbox_id` immediately tells you: "This change only affects this small world"
- Won't affect other projects or system files

### 2. Unified Mechanism

- No need to design a version system for each artifact type
- Unified diff, summary, and rollback mechanisms

### 3. Local / Cloud Consistency

- Local: File system
- Cloud: Volume / Bucket
- Both appear as `sandbox.*` interface to Playbooks / Tools

### 4. Extensibility

- Easy to add new sandbox types
- Unified interface and UI patterns

## 📋 Implementation Checklist

### System-Level Foundation
- [ ] Implement `SandboxManager` core class
- [ ] Implement `Sandbox` base class
- [ ] Implement unified version management
- [ ] Implement storage abstraction (Local / Cloud)

### Specific Types
- [ ] Implement `ThreeJSHeroSandbox`
- [ ] Implement `WritingProjectSandbox`
- [ ] Implement `ProjectRepoSandbox`

### Tool Layer
- [ ] Create `SandboxToolBase`
- [ ] Implement tools for each type
- [ ] Register tools to system

### Migration
- [ ] Migrate `threejs_hero_landing` Playbook
- [ ] Migrate `yearly_personal_book` Playbook
- [ ] Update other related Playbooks

### UI
- [ ] Implement `SandboxViewer` shared component
- [ ] Implement different type preview renderers
- [ ] Implement unified change visualization

## 🚀 Next Steps

1. **Read System Architecture**: [Sandbox System Architecture](./sandbox-system-architecture.md)
2. **Review Implementation Steps**: [Sandbox System Implementation Steps](./sandbox-system-implementation-steps.md)
3. **Start Implementation**: Begin with `SandboxManager` core class

## 📚 Related Documentation

- [Architecture Documentation](../README.md) - Complete system overview
- [Project + Flow Summary](../project-flow/project-flow-summary.md) - Project and Flow architecture

---

**Key Insight**: Sandbox is not a feature specific to a particular scenario, but a **unified abstraction layer for all AI write operations**. This design makes the entire system safer, more consistent, and easier to extend.

