"""
Yearly Book Service
DEPRECATED: This file has been migrated to app.capabilities.yearly_book.services.yearly_book

Please use: from app.capabilities.yearly_book.services.yearly_book import YearlyBookService
"""

# Re-export for backward compatibility
from backend.app.capabilities.yearly_book.services.yearly_book import YearlyBookService

__all__ = ["YearlyBookService"]
