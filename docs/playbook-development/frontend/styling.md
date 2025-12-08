# Styling Guide

Guidelines for styling playbook components.

## Tailwind CSS

All components use Tailwind CSS for styling. Core provides a base configuration.

## Dark Mode Support

Always support dark mode using Tailwind's `dark:` prefix:

```typescript
<div className="bg-white dark:bg-gray-900 text-gray-900 dark:text-gray-100">
  <h1 className="text-gray-800 dark:text-gray-200">Title</h1>
</div>
```

## Color Palette

Use the standard Tailwind color palette:

- **Backgrounds**: `bg-white dark:bg-gray-900`
- **Text**: `text-gray-900 dark:text-gray-100`
- **Borders**: `border-gray-200 dark:border-gray-700`
- **Hover**: `hover:bg-gray-50 dark:hover:bg-gray-800`

## Component Styling Patterns

### Cards

```typescript
<div className="bg-white dark:bg-gray-800 rounded-lg shadow-sm border border-gray-200 dark:border-gray-700 p-4">
  {/* Card content */}
</div>
```

### Buttons

```typescript
<button className="px-4 py-2 bg-blue-600 text-white rounded hover:bg-blue-700 dark:bg-blue-500 dark:hover:bg-blue-600">
  Click me
</button>
```

### Input Fields

```typescript
<input
  className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded bg-white dark:bg-gray-800 text-gray-900 dark:text-gray-100 focus:outline-none focus:ring-2 focus:ring-blue-500"
  type="text"
/>
```

## Layout Patterns

### Flexbox Layouts

```typescript
// Horizontal
<div className="flex items-center gap-4">
  {/* Items */}
</div>

// Vertical
<div className="flex flex-col gap-4">
  {/* Items */}
</div>
```

### Grid Layouts

```typescript
<div className="grid grid-cols-3 gap-4">
  {/* Grid items */}
</div>
```

## Responsive Design

Use Tailwind's responsive prefixes:

```typescript
<div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
  {/* Responsive grid */}
</div>
```

## Spacing

Use consistent spacing scale:

- `p-2`, `p-4`, `p-6` - Padding
- `m-2`, `m-4`, `m-6` - Margin
- `gap-2`, `gap-4`, `gap-6` - Gap

## Typography

```typescript
<h1 className="text-2xl font-bold text-gray-900 dark:text-gray-100">
  Heading 1
</h1>

<p className="text-sm text-gray-600 dark:text-gray-400">
  Body text
</p>
```

## Best Practices

1. **Always support dark mode** - Use `dark:` prefix for all color classes
2. **Use semantic classes** - Prefer semantic color names (gray, blue) over specific shades
3. **Consistent spacing** - Use the same spacing scale throughout
4. **Responsive first** - Design for mobile, enhance for desktop
5. **Accessibility** - Ensure sufficient color contrast

---

**Status**: Content completed with styling patterns

