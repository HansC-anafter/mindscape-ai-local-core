# @mindscape-ai/core

Core utilities and shared components for Mindscape AI.

## Purpose

This package provides a unified import path for shared utilities and components used across Cloud and Local-Core capability packs. It eliminates the need for complex relative path imports like `../../../../lib/api-url`.

## Usage

### API Utilities

```typescript
import { getApiBaseUrl, getApiUrl } from '@mindscape-ai/core';
```

### Context Hooks

```typescript
import {
  useWorkspaceData,
  useWorkspaceDataOptional,
  WorkspaceDataProvider
} from '@mindscape-ai/core';
```

### Note on Shared Components

This package does NOT include capability pack components. If you need to use shared components like `WorkbenchLayout`, import them directly from the capability pack:

```typescript
// Import from video_chapter_studio pack
import { WorkbenchLayout } from '../../video_chapter_studio/components/WorkbenchLayout';
```

## Architecture

- **Local-Core**: Package is part of the monorepo, accessible via `workspace:*` protocol
- **Cloud**: Uses path alias pointing to Local-Core's package directory
- **Installation**: When capability packs are installed, components can use `@mindscape-ai/core` imports which resolve correctly in both environments

## Package Structure

```
packages/core/
├── src/
│   ├── api/              # API utilities (getApiBaseUrl, getApiUrl)
│   ├── contexts/         # React context hooks (WorkspaceDataContext)
│   └── index.ts          # Main entry point
├── package.json
└── tsconfig.json
```

## Development

The package uses re-exports from `web-console/src` for now. In the future, these can be moved directly into the core package for better isolation.
