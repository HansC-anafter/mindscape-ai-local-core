"""
Cloud Connector Service

Execution Transport Adapter for connecting Local-Core to Cloud.
Handles WebSocket connection, task execution, and event reporting.

⚠️ Hard Rule: This is an Execution Transport Adapter, not a Capability Pack.
It does NOT contain Cloud business logic, Cloud UI, or Workspace/Group/Case behavior.
"""

from .connector import CloudConnector
from .transport import TransportHandler
from .heartbeat import HeartbeatMonitor

__all__ = [
    "CloudConnector",
    "TransportHandler",
    "HeartbeatMonitor",
]
