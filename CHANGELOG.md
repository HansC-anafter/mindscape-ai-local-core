# Changelog

All notable changes to Mindscape AI Local Core are documented in this file.

This project adheres to [Semantic Versioning](https://semver.org/).

---

## [Unreleased]

### Added
- Agent dispatch sub-package with modular WebSocket architecture
- Cross-worker WebSocket state management
- Tool RAG filtering for per-task tool selection
- PostgreSQL heartbeat for cross-container runner liveness
- IDE WebSocket client for persistent agent connections

### Changed
- Neutralized Site-Hub references, enforced English-only code comments
- Split `agent_websocket.py` into `agent_dispatch/` sub-package

---

## [v0.5.0] — 2026-01-24

### Added
- Modular capability installer system with comprehensive validation
- `.mindpack` packaging format and install-from-file API
- System tool detection for capability pack installation
- Database migration support within capability packs
- Route conflict detection with manifest prefix validation
- EGB services integration
- UI component database registration for Settings extension points
- `@mindscape-ai/core` shared package for cross-repo imports

### Changed
- Migrated capability installation to modular installer architecture

---

## [v0.4.0] — 2025-12-29

### Added
- P5 multi-agent end-to-end testing framework
- Runtime profile system with execution tracing
- Quality gate events and primary execution tracking
- Engineering safeguards to prevent committing capability-installed files
- Docker PowerShell service status integration

### Fixed
- Runtime profile event store writes and preset field names
- Tool registry fallback behavior

---

## [v0.3.0] — 2025-12-08

### Added
- Phase 5 Flow execution engine with step orchestration
- Phase 4 memory layering for context persistence
- Local-cloud sync mechanism (Phase 1-5)
- Story Thread Engine integration
- Sandbox preview server with centralized port manager
- Node.js 18.x in backend container for sandbox preview

### Changed
- Modularized playbook runner into separate components
- Unified tool execution logic in playbook runner

---

## [v0.2.0] — 2025-12-05

### Added
- Claude-style long-chain execution and Task IR/Handoff
- Pipeline stage events with dynamic content and i18n support
- Database migration support and playbook specs
- Execution plan generation with confidence scoring
- Quick QA response before execution plan generation
- Enhanced playbook, mindscape, and agent web console pages

### Changed
- Refactored playbook loading and execution services
- Updated export, handoff, and suggestion services

---

## [v0.1.0] — 2025-12-02

### Added
- **Core domain**: ExecutionContext, Port interfaces, Local adapters
- **Backend (FastAPI)**: RESTful API with three-layered routes architecture
- **Frontend (Next.js)**: Web Console application
- **Docker Compose**: one-command deployment (`docker compose up`)
- Pack registry with capability suites API
- OCR service for PDF processing
- Architecture documentation and developer guide
- MIT License

---

[Unreleased]: https://github.com/HansC-anafter/mindscape-ai-local-core/compare/v0.5.0...HEAD
[v0.5.0]: https://github.com/HansC-anafter/mindscape-ai-local-core/compare/v0.4.0...v0.5.0
[v0.4.0]: https://github.com/HansC-anafter/mindscape-ai-local-core/compare/v0.3.0...v0.4.0
[v0.3.0]: https://github.com/HansC-anafter/mindscape-ai-local-core/compare/v0.2.0...v0.3.0
[v0.2.0]: https://github.com/HansC-anafter/mindscape-ai-local-core/compare/v0.1.0...v0.2.0
[v0.1.0]: https://github.com/HansC-anafter/mindscape-ai-local-core/releases/tag/v0.1.0
