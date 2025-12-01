# Mindscape AI Local Core

> **Open-source, local-only version of Mindscape AI**

Mindscape AI Local Core is a clean, local-first AI workspace that helps you organize thoughts, manage tasks, and execute workflows through an intelligent conversation interface.

## 🎯 What is Mindscape AI Local Core?

Mindscape AI Local Core is the **open-source foundation** of Mindscape AI. It provides:

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

See [Architecture Documentation](./docs/architecture/) for details.

## 🚀 Quick Start

### Prerequisites

- Python 3.9+
- Node.js 18+ (for frontend)
- SQLite (included with Python)

### Installation

```bash
# Clone the repository
git clone https://github.com/your-org/mindscape-local-core.git
cd mindscape-local-core

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

# Start frontend (from web-console directory)
npm run dev
```

Visit `http://localhost:3000` to access the web interface.

## 📚 Documentation

- [Getting Started](./docs/getting-started/) - Installation and setup guide
- [Architecture](./docs/architecture/) - System architecture and design patterns
- [API Reference](./docs/api/) - Complete API documentation
- [Guides](./docs/guides/) - User guides and tutorials

## 🧩 Port Architecture

Mindscape AI Local Core uses Port interfaces to enable clean separation:

- **IdentityPort**: Get execution context (local adapter returns single-user context)
- **IntentRegistryPort**: Resolve user input to intents (local adapter uses LLM)

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

