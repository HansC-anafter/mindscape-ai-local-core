# Project + Playbook Flow Design Summary

## 🎯 Core Insights

### The Problem

> **Currently, we have "multiple playbooks working in isolation", not "collaborating to build the same house".**

### Three Pain Points

1. **No "Shared World"**
   - Each playbook imagines based on its own inputs, without a single "source of truth" spec/file

2. **No "Execution Order"**
   - Multiple playbooks get triggered simultaneously and run independently
   - LLM mentally orders them, but the execution engine doesn't enforce it

3. **No "Deliverable-Level Container"**
   - Workspace mixes various artifacts: a hero here, a video there, an IG post elsewhere
   - What we need: "These are all components of the same deliverable"

### Solution

Introduce three first-class concepts:
1. **Project / Work Unit** - Deliverable-level container
2. **Playbook Flow** - Playbook group/pipeline
3. **Shared Sandbox** - Deliverable-level file world

## 🏗️ Architecture Overview

### Three-Layer Design

```
Intent Layer
    ↓
Orchestrator
    ↓
Project (deliverable container)
    ↓
Playbook Flow (execution flow)
    ↓
Shared Sandbox (file world)
```

### Core Concepts

#### 1. Project (Deliverable / Worksite)

When a user says "Help me create a webpage about xxx", the system first creates a Project. All subsequent files, sandboxes, and playbook executions are associated with this project.

**Structure:**
```python
Project:
  id: web_page_2025xxxx
  type: web_page
  title: "Webpage about xxx"
  workspace_id: current_workspace_id
  flow_id: web_page_flow
  state: active
```

#### 2. Playbook Flow (Playbook Group)

Instead of multiple playbooks running in parallel chaos, we define nodes and edges. The execution unit is "This Project is running web_page_flow, currently at node A".

**Example:**
```yaml
nodes:
  A: page_outline_md
  B: hero_threejs
  C: sections_react

edges:
  A -> B (B consumes A's md_spec)
  A -> C (C also consumes A's md_spec)
```

#### 3. Shared Sandbox (Deliverable-Level File World)

Create a dedicated sandbox for this Project. All playbooks write to the same project sandbox, naturally enabling file sharing.

**Structure:**
```
sandboxes/web_page/{project_id}/
  spec/page.md          # Output from A
  hero/index.html       # Output from B
  sections/App.tsx      # Output from C
```

## 🔄 Execution Flow Example

### "Help me create a webpage about 'Urban Awareness'"

#### Step 0: Intent Detection
```
User: "Help me create a webpage about 'Urban Awareness'"
→ Intent: web_page_project
→ Orchestrator creates Project + associates web_page_flow
```

#### Step 1: Node A - Page Outline
- Playbook A outputs `spec/page.md`
- Registers artifact: `page_md`
- Flow knows A is complete before scheduling B/C

#### Step 2: Nodes B & C - Hero + Sections
- Both B and C read `page_md` (same spec)
- B outputs `hero/index.html`
- C outputs `sections/App.tsx`
- Can execute in parallel (both only depend on A)

#### Step 3: Workspace UI
```
🧱 Web Page Project – Urban Awareness
Flow: Outline → Hero → Sections
Status: Hero draft complete, Sections 50%
```

## 🎯 Key Value

### From "Working in Isolation" to "Building Together"

**Before:**
- Multiple playbooks running in parallel chaos
- Each imagining based on inputs, no shared world
- No execution order guarantee

**After:**
- Same Project + Sandbox
- Reading the same blueprint (page.md)
- Each doing their part, but sharing the same artifacts
- True "multi-agent" collaboration

### True Multi-Agent Collaboration

> "Multiple agents each receiving keywords and working blindly"
> ↓
> "On the same worksite, reading the same blueprint, each doing their craft, but sharing the same artifacts"

## 🔀 Cross-Workspace Support

### Project Transfer

- Project has `home_workspace_id`
- UI option: "Transfer this Project to 'Web Design Workspace'"
- Original workspace keeps only "result card" and "shortcut"

**Benefits:**
- Control workspace doesn't get cluttered with various artifacts
- Specialized workspaces each have their own Project lists

## 📋 Implementation Priority

### Phase 1: Project Foundation Layer ✅
1. ✅ Define Project data structure
2. ✅ Implement ProjectManager
3. ✅ Implement ArtifactRegistry
4. ✅ Implement ProjectSandboxManager

### Phase 2: Playbook Flow Engine ✅
1. ✅ Define Flow structure
2. ✅ Implement FlowExecutor
3. ✅ Implement dependency checking and node scheduling

### Phase 3: Minimal Flow Implementation ✅
1. ✅ Implement `web_page_flow` (A → B)
2. ✅ Modify `page_outline` playbook
3. ✅ Modify `threejs_hero_landing` playbook
4. ✅ Test complete flow

### Phase 4: Extended Flow ✅
1. ✅ Add node C (sections_react)
2. ✅ Implement parallel execution
3. ✅ Test dependency and artifact sharing

### Phase 5: UI and Cross-Workspace
1. ⏳ Project view UI
2. ⏳ Project cards in Workspace
3. ⏳ Project transfer functionality

## 🔗 Integration with Sandbox System

### Project Sandbox Manager

Projects use the unified SandboxManager but have their own sandbox space:

```python
class ProjectSandboxManager:
    def get_project_sandbox(self, project_id: str) -> Sandbox:
        sandbox_id = f"{project_type}/{project_id}"
        return self.sandbox_manager.get_sandbox(sandbox_id)
```

### Unified Sandbox Capabilities

- All Project sandboxes support version management
- All Project sandboxes support change visualization
- All Project sandboxes support partial modifications

## 📚 Related Documentation

### Core Documentation
- See [Architecture Documentation](../README.md) for complete system overview

### Related Systems
- [Sandbox System Summary](../sandbox/sandbox-system-summary.md) - Sandbox system overview

## 🚀 Getting Started

### Step 1: Understand Architecture

1. Read [System Overview](../system-overview.md) for the complete workflow
2. Understand the relationship between Project, Flow, and Shared Sandbox from this summary
3. Review the example of "creating a webpage" described above

### Step 2: Review Implementation

1. Project data structure is defined in `backend/app/models/project.py`
2. ProjectManager is implemented in `backend/app/services/project/project_manager.py`
3. ArtifactRegistry is implemented in `backend/app/services/project/artifact_registry_service.py`

### Step 3: Use Flow Execution

1. Flow execution is handled by `FlowExecutor` in `backend/app/services/project/flow_executor.py`
2. See [Architecture Documentation](../README.md) for API endpoints and usage

## 💡 Key Insights

### Summary in One Sentence

> **Whenever AI helps you modify something, it should go through the sandbox layer.**
>
> **Whenever multiple playbooks collaborate to complete a deliverable, they should be organized using Project + Flow.**
>
> This transforms your "multi-agent system" from "multiple agents each receiving keywords and working blindly" to "on the same worksite, reading the same blueprint, each doing their craft, but sharing the same artifacts".

---

**This is the key architecture that transforms the mindspace from "working in isolation" to "building together"!** 🏗️

