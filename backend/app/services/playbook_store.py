"""
Playbook Store
⚠️ DEPRECATED: This module has been removed and replaced by PlaybookRegistry and PlaybookService.

All functionality has been migrated to:
- PlaybookDatabaseLoader (backend/app/services/playbook_loaders/database_loader.py)

Use PlaybookService or PlaybookRegistry instead.
"""

raise ImportError(
    "PlaybookStore has been removed. "
    "Use PlaybookService or PlaybookRegistry instead. "
    "See backend/app/services/playbook_service.py and "
    "backend/app/services/playbook_registry.py"
)
