from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Optional


@dataclass
class ExecutionIntentResolution:
    effective_inputs: Dict[str, Any]
    effective_route_metadata: Dict[str, Any] = field(default_factory=dict)
    park_task: bool = False
    blocked_reason: Optional[str] = None
    blocked_payload: Optional[Dict[str, Any]] = None
    resolved_scope: Optional[str] = None
    resolved_device_id: Optional[str] = None
