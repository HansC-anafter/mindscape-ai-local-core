# Mindscape AI Local Core

> **Open-source, local-first AI workspace for AI-driven visible thinking workflows.**

[English](README.md) | [中文](README.zh.md)

`mindscape-ai-local-core` is the open-source, local-first core of **Mindscape AI**.

It turns your long-term goals, projects, and creative themes into a **governable, navigable mindscape**, so the LLM is not just answering isolated prompts, but thinking and acting with you across time.

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

---

## 🧩 Core concepts at a glance

* **Mindscape (workspace)** – the mental space you are working in; holds projects, intents, and execution traces.
* **Intents** – structured "what I want" cards that anchor LLM conversations to your long-term goals.
* **Projects** – containers for related intents and playbooks (e.g., a product launch, a yearly book, a client account).
* **Playbooks** – human-readable + machine-executable workflows (Markdown + YAML frontmatter) that carry capabilities across workspaces.
* **Port/Adapter Architecture** – clean separation between core and external integrations, enabling local-first design with optional cloud extensions.

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

This local core focuses on:

* **Local-first workspace engine**

  * Fast start with Docker
  * All data stays on your machine

* **Playbook runtime**

  * YAML + Markdown playbooks
  * AI roles, tools, and execution traces

* **Project + Flow + Sandbox Architecture (v2.0)**

  * Project lifecycle management
  * Multi-playbook orchestration with dependency resolution
  * Workspace-isolated sandbox for each project
  * Automatic artifact tracking and registration

* **Tool & memory layer**

  * Vector search and semantic capabilities
  * Memory / intent architecture
  * Tool registry and execution

* **Architecture**

  * Port/Adapter pattern for clean boundaries
  * Execution context abstraction
  * Three-layer architecture (Signal, Intent Governance, Execution)

Cloud / multi-tenant features are provided through separate repositories and are **not** included in this repo.

---

## 🚀 Getting started

For installation and quick start, please follow:

1. **Install & prerequisites** – [Installation Guide](./docs/getting-started/installation.md)

2. **Run with Docker** – [Docker Deployment Guide](./docs/getting-started/docker.md) or [Quick Start](./docs/getting-started/quick-start.md)

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
  - Playbooks & Workflows
  - Project + Flow + Sandbox (v2.0)

### Playbook Development
- [Playbook Development](./docs/playbook-development/README.md) - Create and extend playbooks

---

## 🔗 Related projects

* **Mindscape AI Cloud** (private) – multi-tenant cloud version built on top of this core.
* **Mindscape WordPress Plugin** – WordPress integration for Mindscape AI.

---

## 📝 Project status

This is the **open-source, local-only** edition of Mindscape AI:

* ✅ Good for: local experiments, personal workflows, agency sandboxes.
* 🚧 Cloud / multi-tenant features: provided by separate repos, not included here.

---

**Built with ❤️ by the Mindscape AI team**
