# Event Communication

Components communicate via custom browser events. This allows loose coupling between components.

## Event Pattern

Components emit and listen to custom events using the browser's `CustomEvent` API.

## Emitting Events

```typescript
// Emit an event with data
window.dispatchEvent(new CustomEvent('item-selected', {
  detail: {
    item: { id: '1', title: 'Item 1' }
  }
}));
```

## Listening to Events

```typescript
useEffect(() => {
  function handleItemSelect(event: CustomEvent) {
    const item = event.detail.item;
    // Handle selection
    setSelectedItem(item);
  }

  window.addEventListener('item-selected', handleItemSelect as EventListener);

  return () => {
    window.removeEventListener('item-selected', handleItemSelect as EventListener);
  };
}, []);
```

## Common Event Patterns

### Item Selection

```typescript
// Emit
window.dispatchEvent(new CustomEvent('chapter-selected', {
  detail: { chapter }
}));

// Listen
useEffect(() => {
  function handleChapterSelect(event: CustomEvent) {
    const chapter = event.detail.chapter;
    loadChapterContent(chapter);
  }

  window.addEventListener('chapter-selected', handleChapterSelect as EventListener);
  return () => {
    window.removeEventListener('chapter-selected', handleChapterSelect as EventListener);
  };
}, []);
```

### Data Updates

```typescript
// Emit
window.dispatchEvent(new CustomEvent('data-updated', {
  detail: {
    resourceType: 'chapters',
    resourceId: 'chapter-1'
  }
}));

// Listen
useEffect(() => {
  function handleDataUpdate(event: CustomEvent) {
    const { resourceType, resourceId } = event.detail;
    if (resourceType === 'chapters') {
      reloadChapters();
    }
  }

  window.addEventListener('data-updated', handleDataUpdate as EventListener);
  return () => {
    window.removeEventListener('data-updated', handleDataUpdate as EventListener);
  };
}, []);
```

## Event Naming Convention

Use kebab-case for event names:
- ✅ `chapter-selected`
- ✅ `data-updated`
- ✅ `item-created`
- ❌ `chapterSelected` (camelCase)
- ❌ `data_updated` (snake_case)

## Type Safety

Define event types for better TypeScript support:

```typescript
interface ChapterSelectedEvent extends CustomEvent {
  detail: {
    chapter: Chapter;
  };
}

// Usage
window.addEventListener('chapter-selected', (event: Event) => {
  const customEvent = event as ChapterSelectedEvent;
  const chapter = customEvent.detail.chapter;
});
```

## Best Practices

1. **Use descriptive names** - Event names should clearly indicate what happened
2. **Include necessary data** - Pass all data needed by listeners in `detail`
3. **Clean up listeners** - Always remove event listeners in cleanup functions
4. **Document events** - Document which events your component emits/listens to
5. **Avoid deep nesting** - Keep event data structure flat when possible

---

**Status**: Content completed with patterns and best practices

