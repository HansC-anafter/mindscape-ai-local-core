# Yearly Book Example

Complete example of the yearly book playbook.

## Repository Structure

```
mindscape-playbook-yearly-book/
├── package.json
├── playbook/
│   ├── yearly_personal_book.json
│   ├── yearly_personal_book.md
│   ├── i18n/en/yearly_personal_book.md
│   └── UI_LAYOUT.json
├── components/
│   └── yearly-book/
│       ├── ChapterNavigatorSidebar.tsx
│       ├── ChapterEditor.tsx
│       ├── WritingAssistant.tsx
│       └── types.ts
├── backend/
│   └── handlers.py
└── src/
    └── index.ts
```

## Key Features

1. **Chapter Navigation** - Binder-style chapter list
2. **Chapter Editor** - Markdown editor with preview
3. **Writing Assistant** - Key points, related chapters, theme lines

## Implementation Details

### Frontend Components

- `ChapterNavigatorSidebar` - Left sidebar with chapter list
- `ChapterEditor` - Center editor with markdown support
- `WritingAssistant` - Right sidebar with assistance features

### Backend Handler

- `YearlyBookHandler` - Custom endpoints for book structure, key points, related chapters

## See Also

- [Repository](https://github.com/mindscape-ai/playbook-yearly-book)
- [Frontend Guide](../frontend/guide.md)
- [Backend Guide](../backend/guide.md)

---

**Status**: Framework ready, link to actual example repository

