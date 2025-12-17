"""
Sandbox Port Manager

Centralized port allocation for sandbox preview servers.
Supports dynamic allocation, persistence, and conflict resolution.
"""

import os
import logging
import socket
from typing import Optional, Dict, Set
from threading import Lock

logger = logging.getLogger(__name__)


class PortManager:
    """
    Centralized port manager for sandbox preview servers.

    Features:
    - Configurable port range via environment variables
    - Thread-safe port allocation
    - Automatic conflict detection
    - Port reservation and release
    """

    # Environment variable names
    ENV_PORT_START = "SANDBOX_PREVIEW_PORT_START"
    ENV_PORT_END = "SANDBOX_PREVIEW_PORT_END"

    # Default port range (3002-3020, avoids 3000=web-console, 3001=alt)
    DEFAULT_PORT_START = 3002
    DEFAULT_PORT_END = 3020

    _instance: Optional["PortManager"] = None
    _lock = Lock()

    def __new__(cls) -> "PortManager":
        """Singleton pattern for global port management."""
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        """Initialize port manager with configured range."""
        if self._initialized:
            return

        self._initialized = True
        self._allocation_lock = Lock()

        # Load config from environment
        self.port_start = int(os.getenv(self.ENV_PORT_START, self.DEFAULT_PORT_START))
        self.port_end = int(os.getenv(self.ENV_PORT_END, self.DEFAULT_PORT_END))

        # Track allocated ports: sandbox_id -> port
        self._allocated: Dict[str, int] = {}
        # Track reserved ports (allocated but maybe not yet started)
        self._reserved: Set[int] = set()

        logger.info(f"PortManager initialized: range {self.port_start}-{self.port_end}")

    @property
    def available_range(self) -> range:
        """Get the configured port range."""
        return range(self.port_start, self.port_end + 1)

    @property
    def total_ports(self) -> int:
        """Total number of ports in range."""
        return self.port_end - self.port_start + 1

    @property
    def allocated_count(self) -> int:
        """Number of currently allocated ports."""
        return len(self._allocated)

    def _is_port_available(self, port: int) -> bool:
        """Check if port is available (not in use by any process)."""
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.settimeout(0.5)
                result = s.connect_ex(('0.0.0.0', port))
                return result != 0
        except Exception:
            return False

    def allocate(self, sandbox_id: str, preferred_port: Optional[int] = None) -> Optional[int]:
        """
        Allocate a port for a sandbox.

        Args:
            sandbox_id: Unique sandbox identifier
            preferred_port: Optional preferred port (will use if available)

        Returns:
            Allocated port number, or None if no ports available
        """
        with self._allocation_lock:
            # Check if already allocated
            if sandbox_id in self._allocated:
                existing_port = self._allocated[sandbox_id]
                logger.debug(f"Sandbox {sandbox_id} already has port {existing_port}")
                return existing_port

            # Try preferred port first
            if preferred_port and preferred_port in self.available_range:
                if preferred_port not in self._reserved and self._is_port_available(preferred_port):
                    self._allocated[sandbox_id] = preferred_port
                    self._reserved.add(preferred_port)
                    logger.info(f"Allocated preferred port {preferred_port} for sandbox {sandbox_id}")
                    return preferred_port

            # Find first available port in range
            for port in self.available_range:
                if port not in self._reserved and self._is_port_available(port):
                    self._allocated[sandbox_id] = port
                    self._reserved.add(port)
                    logger.info(f"Allocated port {port} for sandbox {sandbox_id}")
                    return port

            logger.warning(f"No available ports for sandbox {sandbox_id}")
            return None

    def release(self, sandbox_id: str) -> bool:
        """
        Release a port allocation.

        Args:
            sandbox_id: Sandbox identifier

        Returns:
            True if released, False if not found
        """
        with self._allocation_lock:
            if sandbox_id not in self._allocated:
                return False

            port = self._allocated.pop(sandbox_id)
            self._reserved.discard(port)
            logger.info(f"Released port {port} from sandbox {sandbox_id}")
            return True

    def get_port(self, sandbox_id: str) -> Optional[int]:
        """Get the port allocated to a sandbox."""
        return self._allocated.get(sandbox_id)

    def get_sandbox(self, port: int) -> Optional[str]:
        """Get the sandbox using a specific port."""
        for sid, p in self._allocated.items():
            if p == port:
                return sid
        return None

    def get_status(self) -> Dict:
        """Get current port manager status."""
        return {
            "port_range": {
                "start": self.port_start,
                "end": self.port_end,
                "total": self.total_ports,
            },
            "allocated": self.allocated_count,
            "available": self.total_ports - self.allocated_count,
            "allocations": dict(self._allocated),
        }

    def cleanup_stale(self) -> int:
        """
        Cleanup stale allocations (ports no longer in use).

        Returns:
            Number of stale allocations cleaned up
        """
        cleaned = 0
        with self._allocation_lock:
            stale = []
            for sandbox_id, port in self._allocated.items():
                if self._is_port_available(port):
                    # Port is free, allocation is stale
                    stale.append(sandbox_id)

            for sandbox_id in stale:
                port = self._allocated.pop(sandbox_id)
                self._reserved.discard(port)
                cleaned += 1
                logger.info(f"Cleaned stale allocation: {sandbox_id} -> {port}")

        return cleaned


# Global singleton instance
port_manager = PortManager()

