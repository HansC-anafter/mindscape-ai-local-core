"""
Cloud Providers Package
Provides abstract interface and implementations for cloud playbook providers
"""

from .base import CloudProvider
from .generic_http import GenericHttpProvider

__all__ = [
    "CloudProvider",
    "GenericHttpProvider",
]

