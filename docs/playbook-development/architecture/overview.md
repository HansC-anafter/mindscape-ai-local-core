# Architecture Overview

## System Architecture

Mindscape AI Playbook system follows a modular architecture:

```
┌─────────────────────────────────────────────────────────┐
│         mindscape-ai-local-core                         │
│  ┌──────────────────────────────────────────────────┐   │
│  │  Core Components (Shared by all playbooks)        │   │
│  │  - common/BinderView.tsx                          │   │
│  │  - common/CorkboardView.tsx                       │   │
│  │  - common/OutlinerView.tsx                        │   │
│  │  - playbook/registry.ts                           │   │
│  │  - playbook/loader.ts                             │   │
│  └──────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────┘
         ↑              ↑              ↑
         │              │              │
    ┌────┴────┐   ┌────┴────┐   ┌────┴────┐
    │ yearly  │   │ course  │   │proposal │
    │  book   │   │writing  │   │writing  │
    └─────────┘   └─────────┘   └─────────┘
         │              │              │
         └──────────────┴──────────────┘
                   依賴 core
```

## Key Components

### 1. Playbook Registry

**Location**: `web-console/src/playbook/registry.ts`

**Purpose**: Register and manage playbook UI components and layouts

**Key Methods**:
- `register(playbook: PlaybookPackage)`: Register a playbook
- `get(playbookCode: string)`: Get a playbook by code
- `getComponent(playbookCode, componentName)`: Get a component

### 2. Playbook Loader

**Location**: `web-console/src/playbook/loader.ts`

**Purpose**: Dynamically load playbooks from NPM packages

**Process**:
1. Scan `node_modules/@mindscape/playbook-*`
2. Load playbook packages
3. Call registration functions
4. Register components and layouts

### 3. Resource Management API

**Location**: `backend/app/routes/core/playbook/resources.py`

**Purpose**: Generic CRUD operations for playbook resources

**Endpoints**:
- `GET /api/v1/workspaces/:workspaceId/playbooks/:playbookCode/resources/:resourceType`
- `POST /api/v1/workspaces/:workspaceId/playbooks/:playbookCode/resources/:resourceType`
- `PUT /api/v1/workspaces/:workspaceId/playbooks/:playbookCode/resources/:resourceType/:resourceId`
- `DELETE /api/v1/workspaces/:workspaceId/playbooks/:playbookCode/resources/:resourceType/:resourceId`

### 4. Playbook Handler System

**Location**: `backend/app/services/playbook_handlers/base.py`

**Purpose**: Hook mechanism for playbook-specific backend logic

**Process**:
1. Playbook implements `PlaybookHandler` base class
2. Handler registers routes in `register_routes()` method
3. Core loads handlers from NPM packages at startup
4. Routes are automatically registered

## Data Flow

### Frontend Flow

```
User Action
  ↓
Playbook Surface Component
  ↓
useAPIClient() → MindscapeAPIClient
  ↓
API Request (auto-handles Local/Cloud)
  ↓
Backend API
```

### Backend Flow

```
API Request
  ↓
Generic Resources API (for simple CRUD)
  OR
Playbook Handler (for complex logic)
  ↓
Storage (workspace storage path)
```

## Storage Structure

```
{workspace_storage_path}/
├── playbooks/
│   ├── yearly_personal_book/
│   │   ├── resources/
│   │   │   ├── chapters/
│   │   │   │   ├── chapter-01.json
│   │   │   │   └── chapter-02.json
│   │   │   ├── book-structure/
│   │   │   │   └── main.json
│   │   │   └── key-points/
│   │   └── metadata.json
│   └── course_writing/
│       └── resources/
│           └── lessons/
```

## Key Principles

1. **Separation**: Common components in core, playbook-specific in independent repos
2. **Dynamic Loading**: Playbooks loaded from NPM packages, no hardcoding
3. **Unified API**: Frontend uses `MindscapeAPIClient`, backend uses unified resource API
4. **No Direct Dependencies**: Playbooks don't depend on Local/Cloud specific implementations

## Related Documentation

- [Repository Structure](./repository-structure.md)
- [Component Separation](./overview.md#component-separation)

---

**Status**: Framework ready, content to be expanded

