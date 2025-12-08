# Component API Reference

Reference for common components provided by core and how to use them in your playbook.

## Common Components

Core provides reusable components in `@mindscape/ai-local-core/components/playbooks/common`:

### BinderView

Tree-like file browser view, similar to Scrivener's Binder.

**Location**: `web-console/src/components/playbooks/common/BinderView.tsx`

**Props**:
```typescript
interface BinderViewProps<T extends ViewItem> {
  items: T[];                           // Items to display
  selectedId?: string | null;           // Selected item ID
  onSelect?: (item: T) => void;        // Selection handler
  onReorder?: (items: T[]) => void;     // Reorder handler
  renderItem?: (item: T, isSelected: boolean) => React.ReactNode;
  getItemIcon?: (item: T) => React.ReactNode;
  getItemStatus?: (item: T) => string;
  allowReorder?: boolean;                // Enable drag-and-drop
}
```

**Example**:
```typescript
import { BinderView } from './core-imports';

<BinderView
  items={chapters}
  selectedId={selectedChapterId}
  onSelect={(chapter) => {
    setSelectedChapterId(chapter.id);
    window.dispatchEvent(new CustomEvent('chapter-selected', {
      detail: { chapter }
    }));
  }}
  onReorder={handleReorder}
  getItemIcon={(chapter) => <span>📄</span>}
  getItemStatus={(chapter) => `${chapter.wordCount} words`}
  allowReorder={true}
/>
```

### CorkboardView

Card view for displaying items as cards.

**Location**: `web-console/src/components/playbooks/common/CorkboardView.tsx`

**Props**:
```typescript
interface CorkboardViewProps<T extends ViewItem> {
  items: T[];
  selectedId?: string | null;
  onSelect?: (item: T) => void;
  onReorder?: (items: T[]) => void;
  renderCard?: (item: T, isSelected: boolean) => React.ReactNode;
  getCardStatus?: (item: T) => string;
  allowReorder?: boolean;
  columns?: number;                      // Number of columns
}
```

**Example**:
```typescript
import { CorkboardView } from './core-imports';

<CorkboardView
  items={lessons}
  selectedId={selectedLessonId}
  onSelect={handleSelect}
  renderCard={(lesson, isSelected) => (
    <div className={`card ${isSelected ? 'selected' : ''}`}>
      <h3>{lesson.title}</h3>
      <p>{lesson.description}</p>
    </div>
  )}
  columns={3}
/>
```

### OutlinerView

Table/outline view for displaying items in a table format.

**Location**: `web-console/src/components/playbooks/common/OutlinerView.tsx`

**Props**:
```typescript
interface OutlinerViewProps<T extends ViewItem> {
  items: T[];
  selectedId?: string | null;
  onSelect?: (item: T) => void;
  onReorder?: (items: T[]) => void;
  columns: Array<{
    key: string;
    label: string;
    render?: (item: T) => React.ReactNode;
    width?: string;
  }>;
  allowReorder?: boolean;
}
```

**Example**:
```typescript
import { OutlinerView } from './core-imports';

<OutlinerView
  items={sections}
  selectedId={selectedSectionId}
  onSelect={handleSelect}
  columns={[
    { key: 'title', label: 'Title', width: '40%' },
    { key: 'status', label: 'Status', width: '20%' },
    { key: 'wordCount', label: 'Words', width: '20%' },
    { key: 'updatedAt', label: 'Updated', width: '20%' }
  ]}
/>
```

## ViewItem Interface

All view components use the `ViewItem` interface:

```typescript
interface ViewItem {
  id: string;
  title: string;
  [key: string]: any;  // Additional properties
}
```

## Using Components in Your Playbook

### 1. Import from core-imports

Create `components/your-playbook/core-imports.ts`:

```typescript
import React, { ComponentType } from 'react';

// Runtime access to core exports
declare global {
  interface Window {
    __mindscapeCore?: {
      BinderView?: ComponentType<any>;
      CorkboardView?: ComponentType<any>;
      OutlinerView?: ComponentType<any>;
    };
  }
}

// Fallback implementations
const FallbackBinderView: ComponentType<any> = ({ items, selectedId, onSelect }) => (
  <div>
    {items.map((item: any) => (
      <div
        key={item.id}
        onClick={() => onSelect?.(item)}
        className={selectedId === item.id ? 'selected' : ''}
      >
        {item.title}
      </div>
    ))}
  </div>
);

export const BinderView: ComponentType<any> = (props: any) => {
  if (typeof window !== 'undefined' && window.__mindscapeCore?.BinderView) {
    const CoreBinderView = window.__mindscapeCore.BinderView;
    return React.createElement(CoreBinderView, props);
  }
  return React.createElement(FallbackBinderView, props);
};
```

### 2. Use in Your Component

```typescript
import { BinderView } from './core-imports';

export function YourComponent() {
  const items = [
    { id: '1', title: 'Item 1' },
    { id: '2', title: 'Item 2' }
  ];

  return (
    <BinderView
      items={items}
      onSelect={(item) => console.log('Selected:', item)}
    />
  );
}
```

## SurfaceLayout

Layout component for arranging components in columns.

**Location**: `web-console/src/components/playbooks/SurfaceLayout.tsx`

**Props**:
```typescript
interface SurfaceLayoutProps {
  type: 'three_column' | 'two_column' | 'single_column';
  children: React.ReactNode;
}
```

**Example**:
```typescript
import { SurfaceLayout } from '@mindscape/ai-local-core/components/playbooks/SurfaceLayout';

<SurfaceLayout type="three_column">
  <YourLeftComponent position="left" />
  <YourCenterComponent position="center" />
  <YourRightComponent position="right" />
</SurfaceLayout>
```

## Best Practices

1. **Always provide fallbacks** - Components should work even if core components aren't available
2. **Use TypeScript** - Define proper types for your items
3. **Handle loading states** - Show loading indicators while fetching data
4. **Error handling** - Display error messages when API calls fail
5. **Dark mode support** - Use Tailwind dark mode classes

---

**Status**: Content completed with API reference and examples

