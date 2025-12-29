# Mindscape AI Local Core

> **Open-source, local-first AI workspace for AI-driven visible thinking workflows.**

[English](README.md) | [中文](README.zh.md)

`mindscape-ai-local-core` is the open-source, local-first core of **Mindscape AI**.

It turns your long-term goals, projects, and creative themes into a **governable, navigable mindscape**, so the LLM is not just answering isolated prompts, but thinking and acting with you across time.

### 🎨 Mind-Lens: A Palette for Rendering

> **Mind-Lens is a Palette for rendering** — a user-authored control surface that *projects* values, aesthetics, and working style into AI execution. It does not "represent you"; it helps you **direct outputs consistently** across workflows.

Mind-Lens works as a **three-layer palette**:

1. **Global Preset** — your baseline palette (how you/your brand generally behaves)
2. **Workspace Override** — project-specific tuning (same person, different context)
3. **Session Override** — temporary knobs for this task (resets after the conversation)

Both the **Mindscape Graph** (author mode) and **Workspace execution** (runtime mode) operate on the same Lens contract — they just edit different scopes of the same palette.

---

## 🧠 AI-driven visible thinking workflow

Instead of "chat in, answer out", Mindscape AI is designed as an **AI-driven visible thinking workflow**:

1. **Capture your mindscape**

   - Turn life themes, long-term projects, and recurring tasks into **intents** and **projects** inside a workspace.

2. **Attach playbooks**

   - Connect each intent/project to reusable **playbooks** (Markdown + YAML) that describe how your AI team should help.

3. **Run, see, and iterate**

   - Let the AI team execute the playbooks, see the **execution trace**, intermediate notes, and outputs, then refine together.

This repo contains the local engine that wires these pieces together: workspace state, intents, the playbook runner, AI roles, and tool connections.

---

## 🔄 Project / Playbook flow

The default mental model for this repo is the **project / playbook flow**:

```text
Project  →  Intents  →  Playbooks  →  AI Team Execution  →  Artifacts & Decisions
```

* **Project** – a long-lived lane such as "Launch my 2026 product", "Write a book every year", or "Run my content studio".
* **Intents** – concrete goals inside that project: "Define outline", "Research competitors", "Draft fundraising page".
* **Playbooks** – reusable workflows that tell your AI team *how* to help (steps, roles, tools).
* **AI Team Execution** – multiple AI roles (planner, writer, analyst…) collaborate, call tools, and produce drafts / plans / checklists.
* **Artifacts & Decisions** – the results are saved back into the workspace and can be exported, synced, or reused.

Examples of built-in system playbooks:

* `daily_planning` – Daily planning & prioritization
* `content_drafting` – Content / copy drafting

You can add your own playbooks to encode your personal workflows, client SOPs, or agency services.

### 🧱 Shareable cognitive modules (even without the cloud)

Although this repo is called *local-core*, it is not limited to "one user on one machine".

The core concepts – **playbooks**, **AI team members**, and **mind-lens / workspace profiles** – are all designed as
**shareable cognitive modules**:

- You can create your own playbooks, AI roles, and mind-lens configurations.
- You can import playbooks and AI team presets created by others (from repos, bundles, or future marketplaces).
- You can treat a "bundle" of `AI team member + mind-lens + playbooks` as a reusable kit for a specific domain
  (e.g., a "book-writing companion", an "SEO advisor", or a "design consultant").

The identity & scope model (owner type, visibility, and `effective_playbooks`) is what makes this exchange safe:

- Locally, it helps you distinguish **system** playbooks, **workspace**-specific flows, and **personal** workflows.
- When you import external playbooks, they can be tagged as `external_provider` and used as templates or forked into
  your own workspace.
- In cloud or multi-tenant deployments, the same model extends to tenants, teams, and shared templates.

In other words, `mindscape-ai-local-core` defines the **world model** for long-lived projects and shareable workflows.
Mindscape AI Cloud is one possible SaaS built on top of this core, but other developers can equally embed this engine
into their own products or commercial offerings.

---

## 🧩 Core concepts at a glance

* **Mindscape (workspace)** – the mental space you are working in; holds projects, intents, and execution traces.
* **Intents** – structured "what I want" cards that anchor LLM conversations to your long-term goals.
* **Projects** – containers for related intents and playbooks (e.g., a product launch, a yearly book, a client account).
* **Playbooks** – human-readable + machine-executable workflows (Markdown + YAML frontmatter) that carry capabilities across workspaces.
* **Port/Adapter Architecture** – clean separation between core and external integrations, enabling local-first design with optional cloud extensions.
* **[Event, Intent Governance, and Memory Architecture](./docs/core-architecture/memory-intent-architecture.md)** – how events, intent analysis, and long-term memory work together.

---

## 📖 Want the deeper "Mindscape Algorithm" story?

The **Mindscape Algorithm** is the conceptual backbone behind this repo. It describes:

* how long-term intents and projects are organized into a governable "mindscape"
* how AI sees and uses that structure instead of only looking at one conversation

See:

* [Mindscape Algorithm notes](./docs/mindscape-algorithm.md)
* [Architecture Documentation](./docs/core-architecture/README.md) - Complete system architecture
* Mindscape AI website: [https://mindscapeai.app](https://mindscapeai.app)

---

## 📦 What's in this repo

In a world where most AI tools stop at "chat + one-shot tools", this repo focuses on **long-lived projects, visible thinking, and governable multi-step workflows**. It's closer to an OS for AI-assisted work than a chatbot wrapper.

This local core focuses on:

* **Local-first workspace engine**

  * Fast start with Docker
  * All data stays on your machine

* **Playbook runtime**

  * YAML + Markdown playbooks (execution spec currently uses JSON, with YAML abstraction planned)
  * AI roles, tools, and execution traces
  * See [Playbooks & Multi-step Workflow Architecture](./docs/core-architecture/playbooks-and-workflows.md) for how playbooks are modeled and executed

* **Project + Flow + Sandbox Architecture (v2.0)**

  * Project lifecycle management
  * Multi-playbook orchestration with dependency resolution
  * Workspace-isolated sandbox for each project
  * Automatic artifact tracking and registration

* **Tool & memory layer**

  * Vector search and semantic capabilities
  * Memory / intent architecture
  * Tool registry and execution

* **Capability-aware staged model routing**

  * Instead of a single global `chat_model`, the local core now uses **capability profiles** (e.g. `FAST`, `STANDARD`, `PRECISE`, `TOOL_STRICT`, `SAFE_WRITE`) to decide which model runs which phase.
  * Phases like **intent analysis**, **tool candidate selection**, **planning**, and **safe writes / tool-calling** can run on different profiles, connected by **stable JSON-based intermediate representations (IR)**.
  * This makes it possible to swap models or providers without rewriting playbooks or control flow logic.
  * **Cost governance**: Each capability profile enforces cost limits (e.g., FAST: $0.002/1k tokens, STANDARD: $0.01/1k tokens, PRECISE: $0.03/1k tokens), and the system automatically selects cost-appropriate models based on task complexity, optimizing for both cost and success rate.

* **Architecture**

  * Port/Adapter pattern for clean boundaries
  * Execution context abstraction
  * Three-layer architecture (Signal, Intent Governance, Execution)

Cloud / multi-tenant features are provided through separate repositories and are **not** included in this repo.

---

## 🚀 Getting started

### Quick Start with Docker (Recommended)

The easiest way to get started is using Docker Compose. **You can start the system immediately after cloning** - API keys are optional and can be configured later through the web interface.

**Windows PowerShell:**
```powershell
# 1. Clone the repository
git clone https://github.com/HansC-anafter/mindscape-ai-local-core.git
cd mindscape-ai-local-core

# 2. Start all services (includes Docker health check)
# If you get an execution policy error, run:
#   powershell -ExecutionPolicy Bypass -File .\scripts\start.ps1
.\scripts\start.ps1
```

**Linux/macOS:**
```bash
# 1. Clone the repository
git clone https://github.com/HansC-anafter/mindscape-ai-local-core.git
cd mindscape-ai-local-core

# 2. Start all services (includes Docker health check)
./scripts/start.sh
```

**Or manually:**
```bash
# 1. Clone the repository
git clone https://github.com/HansC-anafter/mindscape-ai-local-core.git
cd mindscape-ai-local-core

# 2. Start all services
docker compose up -d

# 3. Access the web console
# Frontend: http://localhost:8300
# Backend API: http://localhost:8200
```

> **💡 Note**: API keys (OpenAI or Anthropic) are **optional** for initial startup. The system will start successfully without them, and you can configure them later through the web interface. Some AI features will be unavailable until API keys are configured.

For detailed instructions, see:
- **Docker Deployment** – [Docker Deployment Guide](./docs/getting-started/docker.md)
- **Manual Installation** – [Installation Guide](./docs/getting-started/installation.md)
- **Quick Start** – [Quick Start Guide](./QUICKSTART.md)

Once the stack is running:

1. Open the web console in your browser.
2. Create a workspace and a first **project** (e.g. "Write my 2026 book").
3. Add a few **intents** under that project.
4. Attach or trigger a **playbook** (e.g. `daily_planning` or `content_drafting`) and let the AI team run.
5. Review the execution trace and artifacts produced.

---

## 📚 Documentation

### Getting Started
- [Quick Start](./docs/getting-started/quick-start.md) - Installation and setup guide
- [Docker Deployment](./docs/getting-started/docker.md) - Deploy using Docker Compose
- [Installation Guide](./docs/getting-started/installation.md) - Manual installation instructions

### Core Concepts
- [The Mindscape Algorithm](./docs/mindscape-algorithm.md) - Core philosophy and 3-layer architecture

### Architecture Documentation
- [Architecture Documentation](./docs/core-architecture/README.md) - Complete system architecture, including:
  - Port/Adapter Architecture
  - Memory & Intent Architecture
  - Execution Context
  - Local/Cloud Boundary
  - Playbooks & Workflows (including identity governance and access control)
  - Project + Flow + Sandbox (v2.0)

### Playbook Development
- [Playbook Development](./docs/playbook-development/README.md) - Create and extend playbooks

---

## 🔗 Related projects

* **Mindscape AI Cloud** (private) – multi-tenant cloud version built on top of this core.
* **Mindscape WordPress Plugin** – WordPress integration for Mindscape AI.

---

### 2025-12 system evolution note

## 📦 Capability Packs

Mindscape AI supports **capability packs** - self-contained bundles that extend functionality:

- **Playbooks**: Workflow definitions
- **Tools**: Executable functions
- **Services**: Background services
- **Bootstrap hooks**: Automatic initialization

See [Capability Pack Development Guide](./docs/capability-pack-development-guide.md) for:
- Pack structure and manifest format
- Bootstrap hooks and initialization
- Environment variable configuration
- Development workflow

---

As of December 2025, the local core has been refactored to support **capability-aware, staged model routing** with stable intermediate representations:

- Core phases (intent analysis, tool-candidate selection, planning, safe writes / tool-calls) now produce **typed JSON structures** instead of ad-hoc text.
- Model choice is expressed as high-level **capability profiles** rather than hard-coded model names in playbooks.

This change is mostly architectural: it does not introduce new UI by itself, but it makes the local core easier to extend (or to connect to external telemetry / governance layers in other repositories) without breaking existing workspaces.

---

## 📝 Project status

This is the **open-source, local-only** edition of Mindscape AI:

* ✅ Good for: local experiments, personal workflows, agency sandboxes.
* 🚧 Cloud / multi-tenant features: provided by separate repos, not included here.

---

**Built with ❤️ by the Mindscape AI team**
