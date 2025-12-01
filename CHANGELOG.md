# Changelog

All notable changes to Mindscape AI Local Core will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- Initial open-source release
- Port/Adapter architecture (ExecutionContext, IdentityPort, IntentRegistryPort)
- Local adapters (LocalIdentityAdapter, LocalIntentRegistryAdapter)
- Core services (IntentExtractor, ExecutionCoordinator, ConversationOrchestrator)
- Architecture documentation

## [0.1.0] - 2025-12-02

### Added
- **Core Architecture**
  - `ExecutionContext` - Unified execution context abstraction
  - `IdentityPort` - Abstract interface for identity resolution
  - `IntentRegistryPort` - Abstract interface for intent resolution
  - `LocalIdentityAdapter` - Single-user identity adapter
  - `LocalIntentRegistryAdapter` - Local intent registry adapter

- **Core Services**
  - Intent extraction service
  - Playbook execution coordinator
  - Conversation orchestrator
  - File processor
  - Task manager

- **Documentation**
  - Architecture documentation (Port Architecture, ExecutionContext, Local/Cloud Boundary)
  - Installation guide
  - Quick start guide
  - Security policy
  - Contributing guidelines

### Changed
- Refactored core services to use `ExecutionContext` instead of direct `profile_id`/`workspace_id` parameters
- All core services now support Port/Adapter pattern

### Removed
- Cloud-specific code (site_hub_client, semantic_hub_client)
- Multi-tenant concepts from core domain
- Cloud documentation

---

## Version History

- **0.1.0** (2025-12-02): Initial open-source release with Port/Adapter architecture

---

**Note**: This is a local-only version. Cloud / multi-tenant features are provided through separate repositories.

