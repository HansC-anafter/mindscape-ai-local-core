# Playbook Components

This directory contains playbook-related components for Mindscape AI.

## Structure

```
playbooks/
├── common/              # Common reusable components (in core)
│   ├── BinderView.tsx   # Tree-like file browser view
│   ├── CorkboardView.tsx # Card-based view
│   ├── OutlinerView.tsx  # Table-based outline view
│   └── types.ts         # Common types
├── SurfaceLayout.tsx    # Layout component for playbook surfaces
└── README.md           # This file
```

## Architecture

### Common Components (in Core)

Common components are reusable across all playbooks and reside in `common/`:

- **BinderView**: Tree-like hierarchical view (similar to Scrivener's Binder)
- **CorkboardView**: Card-based grid view (similar to Scrivener's Corkboard)
- **OutlinerView**: Table-based view (similar to Scrivener's Outliner)

These components are generic and accept any data type that extends `ViewItem`.

### Playbook-Specific Components (in Independent Repos)

Playbook-specific components should be implemented in independent repositories:

- `mindscape-playbook-yearly-book/` - Yearly book writing playbook
- `mindscape-playbook-course-writing/` - Course writing playbook
- `mindscape-playbook-proposal-writing/` - Proposal writing playbook

Each playbook repo should:
1. Use common components from `@mindscape/ai-local-core`
2. Implement playbook-specific components
3. Register components via `PlaybookRegistry`

## Usage

### In Playbook Repos

```tsx
import { BinderView, CorkboardView, OutlinerView } from '@mindscape/ai-local-core/playbooks/common';

export function ChapterNavigatorSidebar({ chapters }) {
  return (
    <BinderView
      items={chapters}
      selectedId={selectedChapterId}
      onSelect={handleChapterSelect}
      allowReorder={true}
    />
  );
}
```

## Development Guidelines

1. **Common components** should be generic and reusable
2. **Playbook-specific components** should be in independent repos
3. **Core** only contains infrastructure and common components
4. **Playbooks** are distributed as NPM packages

