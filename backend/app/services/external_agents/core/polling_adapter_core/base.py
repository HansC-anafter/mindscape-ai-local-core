"""
Polling Runtime Adapter

Base class for runtimes dispatched via the REST Polling + DB-primary pipeline.
Concrete adapters only need to set RUNTIME_NAME and optionally override timeouts.

Architecture:
  - DB (TasksStore): source of truth for task state
  - In-memory Future: instant event notification so coroutine doesn't poll
  - submit_result() writes DB first, then resolves Future
"""

import asyncio
import logging
import time
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from backend.app.services.external_agents.core.base_adapter import (
    BaseRuntimeAdapter,
    RuntimeExecRequest,
    RuntimeExecResponse,
)

logger = logging.getLogger(__name__)
