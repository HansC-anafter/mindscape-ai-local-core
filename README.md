# Mindscape AI Local Core

> **Open-source, local-only version of Mindscape AI**

This repository (`mindscape-ai-local-core`) is a clean, local-first AI workspace that helps you organize thoughts, manage tasks, and execute workflows through an intelligent conversation interface.

## 🎯 What is Mindscape AI Local Core?

The `mindscape-ai-local-core` repository is the **open-source foundation** of Mindscape AI. It provides:

- **Intent/Workflow Engine**: AI-powered intent extraction and playbook execution
- **Port/Adapter Architecture**: Clean separation between core and external integrations
- **Local-First Design**: All data stored locally, no cloud dependencies
- **Extensible**: Ready for cloud extensions through adapter pattern

## ✨ Key Features

- **Intent Extraction**: Automatically extract intents and themes from user messages
- **Playbook Execution**: Execute multi-step workflows (playbooks) based on intents
- **Timeline View**: Visualize workspace activity and execution history
- **File Processing**: Analyze and extract content from uploaded files
- **Port Architecture**: Clean abstraction layer for future cloud extensions

## 🏗️ Architecture

Mindscape AI Local Core uses a **Port/Adapter pattern** (Hexagonal Architecture) to maintain clean boundaries:

- **Core Domain**: ExecutionContext, Port interfaces, core services
- **Local Adapters**: Single-user, single-workspace implementations
- **No Cloud Dependencies**: Core is completely independent of cloud/tenant concepts

In addition, `mindscape-ai-local-core` introduces a Playbook-based workflow layer:

- A **Workspace LLM** for human-facing conversations
- A **Playbook LLM + workflow runtime** for executing multi-step workflows (`playbook.run = playbook.md + playbook.json`)

See [Architecture Documentation](./docs/architecture/) for details.

## 🚀 Quick Start

### Prerequisites

- Python 3.9+
- Node.js 18+ (for frontend)
- SQLite (included with Python)

### Installation

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

### Running

```bash
# Start backend (from backend directory)
uvicorn app.main:app --reload

# Start frontend (from web-console directory, in a new terminal)
cd web-console
npm run dev
```

Visit `http://localhost:3000` to access the web interface.

For a more detailed setup guide, see [QUICKSTART.md](./QUICKSTART.md).

## 📚 Documentation

- [Getting Started](./docs/getting-started/quick-start.md) - Installation and setup guide
- [Architecture Overview](./docs/architecture/port-architecture.md) - System architecture and design patterns
- [Playbooks & Multi-step Workflows](./docs/architecture/playbooks-and-workflows.md) - Playbook architecture and workflow execution
- [Memory & Intent Architecture](./docs/architecture/memory-intent-architecture.md) - Event, intent, and memory layer design
- [Local/Cloud Boundary](./docs/architecture/local-cloud-boundary.md) - Architectural separation principles
- [ExecutionContext](./docs/architecture/execution-context.md) - Execution context abstraction

## 🧩 Port Architecture

The local core (`mindscape-ai-local-core`) uses Port interfaces to enable clean separation:

- **IdentityPort**: Get execution context (local adapter returns single-user context)
- **IntentRegistryPort**: Resolve user input to intents (local adapter uses LLM)
- **PlaybookExecutorPort**: Execute Playbook runs (`playbook.run = md + json`) against a local or remote workflow runtime (planned)

Future cloud extensions can implement these ports without modifying core code.

See [Port Architecture](./docs/architecture/port-architecture.md) for details.

## 🤝 Contributing

We welcome contributions! Please see [CONTRIBUTING.md](./CONTRIBUTING.md) for guidelines.

## 📄 License

This project is licensed under the MIT License - see [LICENSE](./LICENSE) for details.

## 🔗 Related Projects

- **Mindscape AI Cloud** (private): Multi-tenant cloud version built on top of this core
- **Mindscape WordPress Plugin**: WordPress integration for Mindscape AI

## 📝 Status

This is the **open-source, local-only version** of Mindscape AI. Cloud / multi-tenant features are provided through separate repositories and are not included in this version.

---

**Built with ❤️ by the Mindscape AI team**
