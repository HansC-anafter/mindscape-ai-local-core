"""
Playbook Loader
⚠️ DEPRECATED: This module has been removed and replaced by PlaybookRegistry and PlaybookService.

All functionality has been migrated to:
- PlaybookFileLoader (backend/app/services/playbook_loaders/file_loader.py)
- PlaybookDatabaseLoader (backend/app/services/playbook_loaders/database_loader.py)
- PlaybookJsonLoader (backend/app/services/playbook_loaders/json_loader.py)

Use PlaybookService or PlaybookRegistry instead.
"""

raise ImportError(
    "PlaybookLoader has been removed. "
    "Use PlaybookService or PlaybookRegistry instead. "
    "See backend/app/services/playbook_service.py and "
    "backend/app/services/playbook_registry.py"
)
