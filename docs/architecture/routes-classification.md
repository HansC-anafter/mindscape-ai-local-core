# Routes Classification: System Core vs Extensible Features

This document classifies all route files in the Mindscape AI Local Core to distinguish between **system core** (required for basic operation) and **extensible features** (can be added/removed later).

## 🔴 System Core (Required - 5 files)

These routes are **essential** for system startup and basic operation. Without them, the application cannot function properly.

### 1. `workspace.py`
- **Purpose**: Workspace management (create, list, get)
- **Core Function**: Core data model for workspaces
- **Status**: ✅ Required

### 2. `playbook.py`
- **Purpose**: Playbook listing and details
- **Core Function**: Core playbook functionality
- **Status**: ✅ Required

### 3. `playbook_execution.py`
- **Purpose**: Playbook execution
- **Core Function**: Core playbook runtime
- **Status**: ✅ Required

### 4. `config.py`
- **Purpose**: System configuration management
- **Core Function**: LLM API key configuration, backend mode
- **Note**: Contains `remote_crs` mode (can be simplified for local-only)
- **Status**: ✅ Required (with simplification)

### 5. `system_settings.py`
- **Purpose**: System settings management
- **Core Function**: System-wide configuration
- **Status**: ✅ Required

## 🟡 Core Features (Extensible - 4 files)

These are **core features** but their implementations can be extended with additional tools/connections.

### 6. `tools.py`
- **Purpose**: Tool management
- **Core Function**: Tool registry and discovery
- **Extensibility**: Tools can be added/removed
- **Status**: ✅ Core (extensible)

### 7. `tool_connections.py`
- **Purpose**: Tool connection management
- **Core Function**: Manage connections to external tools
- **Extensibility**: Connections can be added/removed
- **Status**: ✅ Core (extensible)

### 8. `vector_db.py`
- **Purpose**: Vector database configuration
- **Core Function**: PostgreSQL + pgvector setup
- **Note**: Optional if vector search is not used
- **Status**: ⚠️ Core but optional

### 9. `vector_search.py`
- **Purpose**: Vector search functionality
- **Core Function**: Semantic search in vector database
- **Note**: Optional if vector search is not used
- **Status**: ⚠️ Core but optional

## 🟢 Extensible Feature Modules (10 files)

These are **feature modules** that can be added or removed without affecting core functionality.

### 10. `agent.py`
- **Purpose**: Agent execution
- **Type**: Feature module
- **Status**: 🟢 Extensible

### 11. `ai_roles.py`
- **Purpose**: AI role configuration
- **Type**: Feature module
- **Status**: 🟢 Extensible

### 12. `capability_packs.py`
- **Purpose**: Capability pack management
- **Type**: Feature module
- **Dependency**: Depends on `capabilities` registry
- **Status**: 🟢 Extensible

### 13. `core_export.py`
- **Purpose**: Export/backup functionality
- **Type**: Feature module
- **Status**: 🟢 Extensible

### 14. `external_docs.py`
- **Purpose**: External document synchronization (WordPress)
- **Type**: Feature module
- **Dependency**: Depends on external services (WordPress)
- **Status**: 🟢 Extensible

### 15. `habits.py`
- **Purpose**: Habit learning functionality
- **Type**: Feature module
- **Status**: 🟢 Extensible

### 16. `mindscape.py`
- **Purpose**: Mindscape management
- **Type**: Feature module
- **Dependency**: Depends on `capabilities` registry
- **Status**: 🟢 Extensible (but may be core)

### 17. `playbook_indexing.py`
- **Purpose**: Playbook indexing for search
- **Type**: Feature module (optimization)
- **Status**: 🟢 Extensible

### 18. `playbook_personalization.py`
- **Purpose**: Playbook personalization
- **Type**: Feature module (optimization)
- **Status**: 🟢 Extensible

### 19. `review.py`
- **Purpose**: Review suggestion functionality
- **Type**: Feature module
- **Dependency**: Depends on `capabilities.review`
- **Status**: 🟢 Extensible

### 20. `workflow_templates.py`
- **Purpose**: Workflow template management
- **Type**: Feature module
- **Status**: 🟢 Extensible

## ❓ Needs Confirmation (4 files)

### `course_production/` (3 files)
- `video_segments.py`
- `voice_profiles.py`
- `voice_training_jobs.py`
- **Purpose**: Course production functionality
- **Type**: Business-specific feature
- **Status**: ❓ Needs confirmation if belongs to local-core

### `mindscape.py`
- **Note**: Although it depends on `capabilities`, it may be considered core functionality
- **Status**: ❓ Needs confirmation

## Summary

| Category | Count | Files |
|----------|-------|-------|
| **System Core** | 5 | workspace.py, playbook.py, playbook_execution.py, config.py, system_settings.py |
| **Core (Extensible)** | 4 | tools.py, tool_connections.py, vector_db.py, vector_search.py |
| **Extensible Features** | 10 | agent.py, ai_roles.py, capability_packs.py, core_export.py, external_docs.py, habits.py, mindscape.py, playbook_indexing.py, playbook_personalization.py, review.py, workflow_templates.py |
| **Needs Confirmation** | 4 | course_production/* (3 files), mindscape.py (re-evaluation) |

## Migration Strategy

### Phase 1: System Core (Required)
Copy these 5 files first to ensure basic functionality:
1. `workspace.py`
2. `playbook.py`
3. `playbook_execution.py`
4. `config.py` (simplify remote_crs)
5. `system_settings.py`

### Phase 2: Core Features (Recommended)
Copy these 4 files for full core functionality:
6. `tools.py`
7. `tool_connections.py`
8. `vector_db.py` (if using vector search)
9. `vector_search.py` (if using vector search)

### Phase 3: Extensible Features (Optional)
Copy these 10 files as needed:
10-20. All extensible feature modules

### Phase 4: Confirmation Needed
Decide on:
- `course_production/` files
- `mindscape.py` classification

## Notes

- **Dependencies**: Some routes depend on `capabilities` registry, which is extensible
- **Optional Features**: Vector search and database are optional if not using semantic search
- **External Services**: `external_docs.py` depends on WordPress integration
- **Remote CRS**: `config.py` contains `remote_crs` mode which should be simplified for local-only version

