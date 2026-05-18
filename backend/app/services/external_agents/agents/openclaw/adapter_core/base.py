"""
OpenClaw Runtime Adapter

Adapter for executing OpenClaw within Mindscape's governance layer.
This adapter extends BaseRuntimeAdapter with OpenClaw-specific implementation.
"""

import asyncio
import json
import logging
import os
import shutil
import signal
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from backend.app.services.external_agents.core.base_adapter import (
    BaseRuntimeAdapter,
    RuntimeExecRequest,
    RuntimeExecResponse,
)

logger = logging.getLogger(__name__)
