# Mindscape AI Local Core

> **Open-source, local-only version of Mindscape AI**

[中文](README.zh.md) | [English](README.md)

This repository (`mindscape-ai-local-core`) is a clean, local-first AI workspace that helps you organize thoughts, manage tasks, and execute workflows through an intelligent conversation interface.

## 🧠 What is the Mindscape Algorithm?

**心智空間算法（Mindscape Algorithm）** 是 Mindscape AI 的核心架構理念。

它把使用者的長期意圖、專案主線、創作主題，整理成一個**可治理、可導航的心智空間**，讓 LLM 不再只是回答單一問題，而是圍繞你的整體人生／工作主線一起思考與行動。

The **Mindscape Algorithm** is the core architectural idea behind Mindscape AI.

It organizes a user's long-term intentions, project storylines, and creative themes into a **governable, navigable cognitive space**, and uses this as the backbone for intent-aware LLM agents and workflows.

📖 Learn more: [The Mindscape Algorithm](./docs/mindscape-algorithm.md) | [Mindscape AI Website](https://mindscapeai.app)

## 🎯 What is Mindscape AI Local Core?

The `mindscape-ai-local-core` repository is the **open-source foundation** of Mindscape AI. It provides:

- **Intent/Workflow Engine**: AI-powered intent extraction and playbook execution
- **Port/Adapter Architecture**: Clean separation between core and external integrations
- **Local-First Design**: All data stored locally, no cloud dependencies
- **Extensible**: Ready for cloud extensions through adapter pattern

## ✨ Key Features

- **Intent Extraction**: Automatically extract intents and themes from user messages
- **Playbook Execution**: Execute multi-step workflows (playbooks) based on intents
- **Project + Flow Architecture** (v2.0): Multi-playbook orchestration within project containers
- **Layered Memory System**: Workspace core, project, and member profile memories
- **Timeline View**: Visualize workspace activity and execution history
- **File Processing**: Analyze and extract content from uploaded files
- **Port Architecture**: Clean abstraction layer for future cloud extensions

## 💡 Who is this for?

Mindscape AI is built for people who:

- Often juggle multiple side projects, ideas, and long-term goals, but struggle to see which threads they're actually pushing forward
- Want more than "ask AI a question, get an answer"—they want AI to truly understand what they're working on and who they're becoming
- Prefer incremental change: one step at a time, with more awareness and conscious choices, rather than seeking one big transformation

If this sounds like you, Mindscape AI Local Core gives you a local-first, open-source playground to experiment with your own "mindscape".

## 🏗️ Architecture

### Mindscape Architecture (3 Layers)

Mindscape AI 不是只做一個聊天框，而是圍繞「意圖」設計了三層結構：

1. **Signal Layer — 收集一切線索**

   對話、文件、工具回傳、Playbook 執行結果，都會被轉成輕量的 **IntentSignal**，作為系統理解你在「忙些什麼」的底層訊號。

2. **Intent Governance Layer — 幫你整理主線**

   Signal 會被收斂成 **IntentCard**（長期意圖）與 **短期任務**，並聚成 **IntentCluster**（專案／主題）。這一層就是所謂的「心智空間」，負責維護你的工作與生活主線。

3. **Execution & Semantic Layer — 真的去幹活**

   當某條 Intent 準備好，就交給 Playbook、工具、以及各種語意引擎去執行，包含 RAG 查詢、文件生成、跨工具自動化工作流等。

### Technical Architecture

Mindscape AI Local Core uses a **Port/Adapter pattern** (Hexagonal Architecture) to maintain clean boundaries:

- **Core Domain**: ExecutionContext, Port interfaces, core services
- **Local Adapters**: Single-user, single-workspace implementations
- **No Cloud Dependencies**: Core is completely independent of cloud/tenant concepts

In addition, `mindscape-ai-local-core` introduces a Playbook-based workflow layer:

- A **Workspace LLM** for human-facing conversations
- A **Playbook LLM + workflow runtime** for executing multi-step workflows (`playbook.run = playbook.md + playbook.json`)

### Project + Flow + Sandbox Architecture (v2.0)

Starting from v2.0, Mindscape AI introduces a **Project-based collaboration model**:

- **Workspace**: Long-term collaboration room for teams/clients
- **Project**: Deliverable-level container with its own lifecycle (open, closed, archived)
- **Playbook Flow**: Multi-playbook orchestration with dependency resolution
- **Project Sandbox**: Unified file space shared across all playbooks in a project
- **Layered Memory**: Workspace core, project, and member profile memories

**Key Innovation**: Projects emerge naturally from conversations. When a conversation indicates a project need, the system automatically suggests creating a Project, allowing multiple playbooks to collaborate on the same deliverable.

See [Architecture Documentation](./docs/architecture/) and [Core Architecture Docs](./docs/core-architecture/) for details.

## 🚀 Quick Start

### Option 1: Docker Deployment (Recommended)

The easiest way to get started is using Docker:

```bash
# Clone the repository
git clone https://github.com/HansC-anafter/mindscape-ai-local-core.git
cd mindscape-ai-local-core

# (Optional) Create .env file with your API keys
# You can also configure API keys through the web interface after starting services
cp .env.example .env
# Edit .env and add your OPENAI_API_KEY or ANTHROPIC_API_KEY

# Start all services
docker compose up -d

# View logs
docker compose logs -f
```

Access the application:
- **Frontend**: http://localhost:3001 (Docker deployment, production-like)
- **Backend API**: http://localhost:8000
- **API Docs**: http://localhost:8000/docs

See [Docker Deployment Guide](./docs/getting-started/docker.md) for detailed instructions.

### Option 2: Manual Installation

#### Prerequisites

- Python 3.9+
- Node.js 18+ (for frontend)
- SQLite (included with Python)

#### Installation

```bash
# Clone the repository
git clone https://github.com/HansC-anafter/mindscape-ai-local-core.git
cd mindscape-ai-local-core

# Install backend dependencies
cd backend
pip install -r requirements.txt

# Install frontend dependencies
cd ../web-console
npm install
```

#### Running

```bash
# Start backend (from backend directory)
uvicorn app.main:app --reload

# Start frontend (from web-console directory, in a new terminal)
cd web-console
npm run dev
```

Visit `http://localhost:3000` to access the web interface (local dev server, frontend `npm run dev`).

For a more detailed setup guide, see [QUICKSTART.md](./QUICKSTART.md) or [Installation Guide](./docs/getting-started/installation.md).

## 📚 Documentation

### Getting Started
- [Getting Started](./docs/getting-started/quick-start.md) - Installation and setup guide
- [Docker Deployment](./docs/getting-started/docker.md) - Deploy using Docker Compose
- [Installation Guide](./docs/getting-started/installation.md) - Manual installation instructions

### Core Concepts
- [The Mindscape Algorithm](./docs/mindscape-algorithm.md) - Core philosophy and 3-layer architecture
- [Mindscape AI Website](https://mindscapeai.app) - Complete technical whitepaper and product introduction (coming soon)

### Architecture Documentation
- [Architecture Documentation](./docs/core-architecture/README.md) - Complete system architecture, including:
  - Port/Adapter Architecture
  - Memory & Intent Architecture
  - Execution Context
  - Local/Cloud Boundary
  - Playbooks & Workflows
  - Project + Flow + Sandbox (v2.0)

## 🧩 Port Architecture

The local core (`mindscape-ai-local-core`) uses Port interfaces to enable clean separation:

- **IdentityPort**: Get execution context (local adapter returns single-user context)
- **IntentRegistryPort**: Resolve user input to intents (local adapter uses LLM)
- **PlaybookExecutorPort**: Execute Playbook runs (`playbook.run = md + json`) against a local or remote workflow runtime (✅ implemented)

**Future Plans**:
- Custom contextual UI panels for playbook execution

Future cloud extensions can implement these ports without modifying core code.

See [Port Architecture](./docs/architecture/port-architecture.md) for details.

## 🔬 For Developers / Researchers

Mindscape AI 把自己定位在「**intent-first 的 LLM agent 架構**」：

* 受 Conceptual Spaces & Cognitive Maps 啟發，我們把 IntentCard / IntentCluster 視為一張可導航的 **意圖地圖**。
* 受 BDI 與階層式強化學習（options）啟發，我們把 Intent Layer 視為高階決策層，Playbook 與執行引擎則專心做執行。
* 受 Active Inference 啟發，我們把使用者的偏好與長期目標，收斂成一組能引導「下一步最值得做什麼」的偏好分佈。

如果你對這些主題有興趣，可以參考 [Mindscape AI Website](https://mindscapeai.app) 了解完整設計與技術白皮書（即將推出）。

## 🤝 Contributing

We welcome contributions! Please see [CONTRIBUTING.md](./CONTRIBUTING.md) for guidelines.

## 📧 Contact & Community

Maintainer: [Hans Huang](https://github.com/HansC-anafter)

- 🐞 **Bug report or feature request**
  → Please open a [GitHub Issue](/issues).

- 💬 **Questions / ideas / sharing your use cases**
  → Use [GitHub Discussions](/discussions) (recommended).

- 🤝 **Collaboration & commercial use** (agencies, teams, hardware partners, etc.)
  → Contact: `dev@mindscapeai.app`

> Please avoid sending support requests to personal emails or social media.

> Using Issues/Discussions helps the whole community benefit from the answers.

## 📄 License

This project is licensed under the MIT License - see [LICENSE](./LICENSE) for details.

## 🔗 Related Projects

- **Mindscape AI Cloud** (private): Multi-tenant cloud version built on top of this core
- **Mindscape WordPress Plugin**: WordPress integration for Mindscape AI

## 📝 Status

This is the **open-source, local-only version** of Mindscape AI. Cloud / multi-tenant features are provided through separate repositories and are not included in this version.

---

**Built with ❤️ by the Mindscape AI team**
