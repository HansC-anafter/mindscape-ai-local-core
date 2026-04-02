"""
Compatibility shim for the manifest-backed ``core_llm`` capability namespace.

Edit ``backend.app.system_capabilities.core_llm.services.structured`` instead.
"""

import sys

from backend.app.system_capabilities.core_llm.services import structured as _impl

sys.modules[__name__] = _impl
