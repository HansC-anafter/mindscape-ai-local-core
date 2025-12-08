# Handler Development

## Overview

Handlers provide playbook-specific backend logic when the generic resources API is not sufficient.

## When to Use Handlers

Use handlers for:
- Complex business logic
- Custom API endpoints
- Cross-resource operations

## Handler Base Class

```python
from mindscape_ai_local_core.app.services.playbook_handlers.base import PlaybookHandler
from fastapi import APIRouter

class YourPlaybookHandler(PlaybookHandler):
    def get_playbook_code(self) -> str:
        return "your_playbook"

    def register_routes(self, router: APIRouter) -> None:
        # Register your routes here
        pass
```

## Registration

Core automatically loads handlers from `backend/handlers.py`:

```python
# backend/handlers.py
def register_handler() -> PlaybookHandler:
    return YourPlaybookHandler()
```

## Route Registration

Routes are automatically prefixed:
```
/api/v1/workspaces/{workspace_id}/playbooks/{playbook_code}/your-route
```

## Example

```python
class YearlyBookHandler(PlaybookHandler):
    def get_playbook_code(self) -> str:
        return "yearly_personal_book"

    def register_routes(self, router: APIRouter) -> None:
        @router.get("/book-structure")
        async def get_book_structure(workspace_id: str):
            # Implementation
            pass

        @router.get("/chapters/{chapter_id}/key-points")
        async def get_key_points(workspace_id: str, chapter_id: str):
            # Implementation
            pass
```

## Accessing Core Services

```python
from mindscape_ai_local_core.app.services.mindscape_store import MindscapeStore
from mindscape_ai_local_core.app.services.storage_path_resolver import StoragePathResolver

store = MindscapeStore()
# Use store methods
```

## Related Documentation

- [Backend Guide](./guide.md) - General backend development
- [Resources API](./resources-api.md) - Generic resource API

---

**Status**: Framework ready, content to be expanded with detailed examples

