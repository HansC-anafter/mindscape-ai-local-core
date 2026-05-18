"""
HostBridgeTaskExecutor — host-side task execution engine for WS-dispatched CLI surfaces.

Receives dispatch payloads from the WebSocket client and executes coding
tasks. Supports progress reporting via a callback function.

Architecture:
    HostBridgeWSClient -> _handle_dispatch -> HostBridgeTaskExecutor.__call__
                                                       |
                                                  execute task
                                                       |
                                                  return result dict

Usage:
    executor = HostBridgeTaskExecutor(workspace_root="/path/to/project")
    client = HostBridgeWSClient(
        workspace_id="ws-123",
        surface="codex_cli",
        task_handler=executor,
    )
"""

import asyncio
import base64
import json
import logging
import os
import shlex
import shutil
import socket
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Coroutine, Dict, List, Optional

from backend.app.services.external_agents.bridge.codex_cli_runner import (
    DEFAULT_CLI_STALL_TIMEOUT_SECONDS,
    cli_activity_signature,
    clip_cli_stream,
    extract_codex_cli_error,
    resolve_codex_cli_binary,
    resolve_codex_cli_output,
    tail_cli_stream,
    wait_for_cli_subprocess_activity,
)
from backend.app.services.codex_runtime_failure_classifier import (
    classify_codex_cli_runtime_failure,
    should_retry_codex_runtime_fault,
)

logger = logging.getLogger("task_executor")


# ============================================================
#  Configuration
# ============================================================

DEFAULT_TASK_TIMEOUT = 600  # 10 minutes
MAX_OUTPUT_SIZE = 100_000  # characters
CODEX_POOL_MAX_TASK_ATTEMPTS = 3
DEFAULT_AUTH_BUNDLE_TIMEOUT_SECONDS = 20.0
DEFAULT_AUTH_BUNDLE_MAX_ATTEMPTS = 3
DEFAULT_AUTH_BUNDLE_RETRY_DELAY_SECONDS = 0.5
DEFAULT_QUOTA_REPORT_TIMEOUT_SECONDS = 10.0
DEFAULT_QUOTA_REPORT_MAX_ATTEMPTS = 2
