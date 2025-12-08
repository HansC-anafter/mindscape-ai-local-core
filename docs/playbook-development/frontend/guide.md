# Frontend Development Guide

## Overview

This guide explains how to create UI components for your playbook.

## Core Concepts

### 1. Component Registration

Components are registered in the playbook registration function:

```typescript
// src/index.ts
import { YourComponent } from '../components/your-playbook';

export function registerYourPlaybook(registry: PlaybookRegistry): void {
  registry.register({
    playbookCode: 'your_playbook',
    components: {
      'YourComponent': YourComponent,
    }
  });
}
```

### 2. Using Core Components

Core provides reusable components in `@mindscape/ai-local-core/components/playbooks/common`:

- `BinderView` - Tree-like file browser view
- `CorkboardView` - Card view
- `OutlinerView` - Table/outline view

### 3. API Client

Use `useAPIClient()` hook to access the unified API client:

```typescript
import { useAPIClient } from './core-imports';

function YourComponent() {
  const apiClient = useAPIClient();

  const response = await apiClient.get(
    `/api/v1/workspaces/${workspaceId}/playbooks/your_playbook/resources/items`
  );
}
```

### 4. Event Communication

Components communicate via custom events:

```typescript
// Emit event
window.dispatchEvent(new CustomEvent('item-selected', {
  detail: { item }
}));

// Listen to event
useEffect(() => {
  function handleItemSelect(event: CustomEvent) {
    const item = event.detail.item;
    // Handle selection
  }

  window.addEventListener('item-selected', handleItemSelect as EventListener);
  return () => {
    window.removeEventListener('item-selected', handleItemSelect as EventListener);
  };
}, []);
```

## Component Structure

### Basic Component Template

```typescript
'use client';

import React, { useState, useEffect } from 'react';
import { useAPIClient } from './core-imports';

interface YourComponentProps {
  workspaceId: string;
  playbookCode: string;
  config: Record<string, any>;
  position?: string;
}

export function YourComponent({
  workspaceId,
  playbookCode,
  config
}: YourComponentProps) {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const apiClient = useAPIClient();

  useEffect(() => {
    loadData();
  }, [workspaceId]);

  async function loadData() {
    try {
      const response = await apiClient.get(
        `/api/v1/workspaces/${workspaceId}/playbooks/${playbookCode}/resources/items`
      );
      if (response.ok) {
        const data = await response.json();
        setData(data);
      }
    } catch (error) {
      console.error('Failed to load data:', error);
    } finally {
      setLoading(false);
    }
  }

  if (loading) {
    return <div>Loading...</div>;
  }

  return (
    <div className="h-full flex flex-col">
      {/* Your component UI */}
    </div>
  );
}

export default YourComponent;
```

## Using Common Components

### BinderView Example

```typescript
import { BinderView } from './core-imports';

<BinderView
  items={chapters}
  selectedId={selectedId}
  onSelect={handleSelect}
  onReorder={handleReorder}
  getItemIcon={(item) => <span>📄</span>}
  getItemStatus={(item) => `${item.wordCount} words`}
  allowReorder={true}
/>
```

## Styling

Components should use Tailwind CSS classes and support dark mode:

```typescript
<div className="bg-white dark:bg-gray-900 text-gray-900 dark:text-gray-100">
  {/* Content */}
</div>
```

## Related Documentation

- [Component API](./components.md) - Component API reference
- [Events](./events.md) - Event communication details
- [Styling](./styling.md) - Styling guidelines

---

**Status**: Framework ready, content to be expanded with detailed examples

