# Mindscape AI Glossary / 術語表

> **Version**: 1.0
> **Last Updated**: 2026-01-31

This glossary defines the core terminology used in Mindscape AI. Understanding these terms will help you navigate the documentation and make the most of the platform.

---

## Core Concepts / 核心概念

### Mindscape

| Language | Definition |
|----------|------------|
| **English** | A governable, navigable mental workspace that organizes your values, preferences, projects, and long-term goals. Unlike a simple "workspace" or "dashboard", a Mindscape is designed to be a **living mental map** that evolves with you over time. |
| **中文** | 一個可治理、可導航的心智工作空間，整理你的價值觀、偏好、專案與長期目標。不同於簡單的「工作區」或「儀表板」，Mindscape 被設計為一個隨時間與你一同演化的**動態心智地圖**。 |

**Avoid using**: Dashboard, Workspace (when referring to the mental map concept)

**Code mapping**: `Workspace` model (the container), but conceptually "Mindscape" emphasizes the mental model aspect.

---

### Intent

| Language | Definition |
|----------|------------|
| **English** | A structured representation of "what you want to achieve" — more than a task or to-do item. Intents are versionable, traceable cards that anchor LLM conversations to your long-term goals. |
| **中文** | 「你想達成什麼」的結構化表示 —— 不只是任務或待辦事項。Intent 是可版本化、可追蹤的卡片，把 LLM 對話錨定在你的長期目標上。 |

**Avoid using**: Task, To-do

**Code mapping**: `IntentCard` model, stored in workspace events

**Key features**:
- Versionable (v1.0 → v1.1)
- Rollback-able
- Contains success criteria and forbidden actions

---

### Playbook

| Language | Definition |
|----------|------------|
| **English** | A reusable, human-readable workflow definition (Markdown + YAML) that describes how your AI team should help with a specific type of work. Playbooks carry capabilities across workspaces and can be shared. |
| **中文** | 可重用、人類可讀的工作流定義（Markdown + YAML），描述你的 AI 小隊如何協助完成特定類型的工作。Playbook 可以跨工作區攜帶能力，也可以分享。 |

**Avoid using**: Template, Script

**Code mapping**: `Playbook` model, `PlaybookRunner` service

**Examples**: `daily_planning`, `content_drafting`, `yearly_personal_book`

---

### Mind-Lens

| Language | Definition |
|----------|------------|
| **English** | A **palette for rendering** AI outputs — a user-authored control surface that projects your values, aesthetics, and working style into AI execution. Mind-Lens does not "represent you"; it helps you **direct outputs consistently** across workflows. |
| **中文** | AI 輸出的**調色盤** —— 一個由使用者定義的控制介面，把你的價值觀、美學偏好、工作風格投射到 AI 執行中。Mind-Lens 不是「代表你」，而是幫你在各種工作流中**一致地導演輸出**。 |

**Avoid using**: Settings, Preferences

**Code mapping**: `MindLens` model, three-layer composition (Global → Workspace → Session)

**Three-layer structure**:
1. **Global Preset** — Your baseline palette
2. **Workspace Override** — Project-specific tuning
3. **Session Override** — Temporary knobs for this task

---

### Execution Trace

| Language | Definition |
|----------|------------|
| **English** | A visible, inspectable record of how a Playbook or AI action was executed. Unlike simple logs, Execution Traces are designed for human review, debugging, and governance. |
| **中文** | Playbook 或 AI 動作執行過程的可視化、可檢視紀錄。不同於簡單的日誌，Execution Trace 是為人類審閱、除錯與治理而設計的。 |

**Avoid using**: Log, History (when emphasizing visible thinking)

**Code mapping**: `ExecutionTrace` in playbook results, stored as workspace events

---

## Asset Provenance Concepts / 資產溯源概念

### Asset

| Language | Definition |
|----------|------------|
| **English** | Any content unit produced or managed within Mindscape — documents, media, code, configurations. Assets are the top-level container for version control. |
| **中文** | 在 Mindscape 中產生或管理的任何內容單元 —— 文件、媒體、程式碼、設定。Asset 是版本控管的頂層容器。 |

---

### Revision

| Language | Definition |
|----------|------------|
| **English** | A version of an Asset. Each time an Asset is meaningfully updated, a new Revision is created. |
| **中文** | Asset 的一個版本。每當 Asset 有意義地更新時，就會建立新的 Revision。 |

---

### Segment

| Language | Definition |
|----------|------------|
| **English** | A sub-division of an Asset that can be independently governed. For audio/video, this might be a time range (e.g., "35-78 seconds"). For text, this might be a paragraph or section. Segment-level governance enables fine-grained rollback. |
| **中文** | Asset 的可獨立治理的子劃分。對於音視頻，這可能是一個時間範圍（如「35-78 秒」）。對於文字，可能是一個段落或章節。Segment 層級的治理讓細粒度回滾成為可能。 |

**Avoid using**: Chunk, Part (when emphasizing governance)

---

### Take

| Language | Definition |
|----------|------------|
| **English** | A single generation attempt for a Segment. When AI generates content, each attempt is a Take. Multiple Takes may exist for the same Segment, and you can compare them before choosing one. |
| **中文** | 針對一個 Segment 的單次生成嘗試。當 AI 生成內容時，每次嘗試都是一個 Take。同一個 Segment 可能有多個 Take，你可以在選擇前比較它們。 |

**Avoid using**: Version, Try (when in asset provenance context)

---

### Selection

| Language | Definition |
|----------|------------|
| **English** | The currently chosen Take for a Segment. "Rollback" in Mindscape means switching the Selection to a different Take — no Take is ever deleted. |
| **中文** | 某個 Segment 當前選定的 Take。在 Mindscape 中「回滾」意味著把 Selection 切換到不同的 Take —— 沒有任何 Take 會被刪除。 |

**Avoid using**: Choice, Pick (when in asset provenance context)

---

## Governance Concepts / 治理概念

### Human Governance Layer

| Language | Definition |
|----------|------------|
| **English** | The architectural layer that ensures every AI action is traceable, versionable, and controllable by humans. Includes Intent Governance, Lens Governance, Trust Governance, and Asset Governance. |
| **中文** | 確保每個 AI 動作都可被人類追溯、版本化、控制的架構層。包含意圖治理、視角治理、信任治理與資產治理。 |

---

### Intent Governance

| Language | Definition |
|----------|------------|
| **English** | Governing "why we're doing this" — Intent versioning, success criteria, forbidden actions. |
| **中文** | 治理「為什麼要做這個」—— Intent 版本化、成功標準、禁止事項。 |

---

### Lens Governance

| Language | Definition |
|----------|------------|
| **English** | Governing "how AI should behave" — Mind-Lens versioning, A/B testing, style consistency. |
| **中文** | 治理「AI 該怎麼表現」—— Mind-Lens 版本化、A/B 測試、風格一致性。 |

---

### Trust Governance

| Language | Definition |
|----------|------------|
| **English** | Governing "is this safe to run" — Preflight checks, risk labels, audit trail. |
| **中文** | 治理「這個執行安全嗎」—— 預檢查、風險標籤、審計軌跡。 |

---

### Asset Governance

| Language | Definition |
|----------|------------|
| **English** | Governing "how content evolved" — Segment-level provenance, Take/Selection management, rollback. |
| **中文** | 治理「內容怎麼演化的」—— Segment 級溯源、Take/Selection 管理、回滾。 |

---

## Architecture Concepts / 架構概念

### Local-first

| Language | Definition |
|----------|------------|
| **English** | Data stays on your machine by default. Works offline. You own everything. External APIs (like LLM providers) are called only when explicitly needed. |
| **中文** | 資料預設留在你的機器上。可離線運作。你擁有一切。只有在明確需要時才會呼叫外部 API（如 LLM 供應商）。 |

---

### Capability Pack

| Language | Definition |
|----------|------------|
| **English** | A self-contained bundle that extends Mindscape's functionality. May include Playbooks, Tools, Services, and Bootstrap hooks. Packs can be installed from various sources (system, workspace, external). |
| **中文** | 擴展 Mindscape 功能的自包含套件。可包含 Playbook、工具、服務與 Bootstrap hooks。Pack 可從多種來源安裝（系統、工作區、外部）。 |

---

### Project

| Language | Definition |
|----------|------------|
| **English** | A deliverable-level container with its own lifecycle (open → closed → archived). Projects hold related Intents and Playbook Flows, and have an isolated Sandbox for files. |
| **中文** | 具有自己生命週期（open → closed → archived）的交付物級容器。Project 容納相關的 Intent 與 Playbook Flow，並擁有獨立的 Sandbox 存放檔案。 |

---

### Sandbox

| Language | Definition |
|----------|------------|
| **English** | A workspace-isolated file space for each Project. Path structure: `sandboxes/{workspace_id}/{project_type}/{project_id}/`. All AI-generated artifacts are saved here. |
| **中文** | 每個 Project 的工作區隔離檔案空間。路徑結構：`sandboxes/{workspace_id}/{project_type}/{project_id}/`。所有 AI 生成的產出都儲存在這裡。 |

---

### Mind-Model VC

| Language | Definition |
|----------|------------|
| **English** | Version control for mind models — organizes user-provided clues (values, preferences, context) into reviewable, adjustable, and rollback-able mind state recipes with version history. |
| **中文** | 心智模型的版本控管 —— 將使用者提供的線索（價值觀、偏好、情境）整理成可回顧、可調整、可回滾的心智狀態配方，並保留版本歷史。 |

---

## Terminology Comparison Table / 術語對照表

| Mindscape Term | Avoid | Common Equivalents | Notes |
|---------------|-------|-------------------|-------|
| Mindscape | Dashboard, Workspace | Mental workspace | Emphasizes navigable mental map |
| Intent | Task, To-do | Goal, Objective | Structured, versionable |
| Playbook | Template, Script | Workflow, SOP | Human + machine readable |
| Mind-Lens | Settings, Preferences | Style guide, Persona | Rendering palette |
| Execution Trace | Log, History | Audit trail | Visible thinking |
| Segment | Chunk, Part | Section | Governance unit |
| Take | Version, Try | Attempt | Generation instance |
| Selection | Choice, Pick | Current version | Active Take |

---

## See Also

- [Mind-Lens Architecture](./core-architecture/mind-lens.md)
- [Memory & Intent Architecture](./core-architecture/memory-intent-architecture.md)
- [Playbooks & Workflows](./core-architecture/playbooks-and-workflows.md)
- [Governance Decision & Risk Control Layer](./core-architecture/governance-decision-risk-control-layer.md)
