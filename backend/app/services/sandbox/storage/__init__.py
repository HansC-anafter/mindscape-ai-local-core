"""
Storage abstraction layer for Sandbox system

Supports local file system and cloud storage backends.
"""

from backend.app.services.sandbox.storage.base_storage import BaseStorage
from backend.app.services.sandbox.storage.local_storage import LocalStorage

__all__ = [
    "BaseStorage",
    "LocalStorage",
]

