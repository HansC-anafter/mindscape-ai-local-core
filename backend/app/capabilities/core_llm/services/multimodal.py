"""
Compatibility shim for the manifest-backed ``core_llm`` capability namespace.

Edit ``backend.app.system_capabilities.core_llm.services.multimodal`` instead.
"""

import sys

from backend.app.system_capabilities.core_llm.services import multimodal as _impl

sys.modules[__name__] = _impl
