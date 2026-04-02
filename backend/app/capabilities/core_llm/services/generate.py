"""
Compatibility shim for the manifest-backed ``core_llm`` capability namespace.

Edit ``backend.app.system_capabilities.core_llm.services.generate`` instead.
"""

import sys

from backend.app.system_capabilities.core_llm.services import generate as _impl

sys.modules[__name__] = _impl
