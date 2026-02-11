"""
Offline Mode
Manages offline mode detection and graceful degradation
"""

import asyncio
import logging
from enum import Enum
from datetime import datetime, timedelta, timezone


def _utc_now():
    """Return timezone-aware UTC now."""
    return datetime.now(timezone.utc)
from typing import Optional, Callable, List
from dataclasses import dataclass

try:
    import httpx
except ImportError:
    httpx = None

logger = logging.getLogger(__name__)


class ConnectivityStatus(Enum):
    """Network connectivity status"""
    ONLINE = "online"
    OFFLINE = "offline"
    DEGRADED = "degraded"


@dataclass
class ConnectivityState:
    """Current connectivity state"""
    status: ConnectivityStatus
    last_check: datetime
    consecutive_failures: int
    last_error: Optional[str] = None


class ConnectivityMonitor:
    """Monitors network connectivity status"""

    def __init__(
        self,
        health_check_url: str = "https://api.mindscape.ai/health",
        check_interval: timedelta = timedelta(minutes=5),
        timeout: timedelta = timedelta(seconds=5),
        failure_threshold: int = 3,
    ):
        """
        Initialize connectivity monitor

        Args:
            health_check_url: Health check endpoint URL
            check_interval: Interval between health checks
            timeout: Request timeout
            failure_threshold: Number of consecutive failures before marking offline
        """
        if not httpx:
            logger.warning("httpx not available, connectivity monitoring disabled")
            self._httpx_available = False
        else:
            self._httpx_available = True

        self.health_check_url = health_check_url
        self.check_interval = check_interval
        self.timeout = timeout
        self.failure_threshold = failure_threshold

        self.state = ConnectivityState(
            status=ConnectivityStatus.OFFLINE,
            last_check=_utc_now(),
            consecutive_failures=0,
        )

        self._status_callbacks: List[Callable[[ConnectivityStatus, ConnectivityStatus], None]] = []
        self._monitoring_task: Optional[asyncio.Task] = None
        self._stop_monitoring = False

    def add_status_callback(
        self,
        callback: Callable[[ConnectivityStatus, ConnectivityStatus], None]
    ):
        """
        Add callback for status changes

        Args:
            callback: Function called when status changes (old_status, new_status)
        """
        self._status_callbacks.append(callback)

    def remove_status_callback(
        self,
        callback: Callable[[ConnectivityStatus, ConnectivityStatus], None]
    ):
        """Remove status change callback"""
        if callback in self._status_callbacks:
            self._status_callbacks.remove(callback)

    async def check_connectivity(self) -> ConnectivityStatus:
        """
        Check current connectivity status

        Returns:
            Current connectivity status
        """
        if not self._httpx_available:
            return ConnectivityStatus.OFFLINE

        try:
            async with httpx.AsyncClient(timeout=self.timeout.total_seconds()) as client:
                response = await client.get(self.health_check_url)

                if response.status_code == 200:
                    old_status = self.state.status
                    self.state.status = ConnectivityStatus.ONLINE
                    self.state.consecutive_failures = 0
                    self.state.last_error = None
                    self.state.last_check = _utc_now()

                    if old_status != ConnectivityStatus.ONLINE:
                        self._notify_status_change(old_status, ConnectivityStatus.ONLINE)

                    return ConnectivityStatus.ONLINE
                else:
                    old_status = self.state.status
                    self.state.consecutive_failures += 1
                    self.state.last_error = f"HTTP {response.status_code}"
                    self.state.last_check = _utc_now()

                    if self.state.consecutive_failures >= self.failure_threshold:
                        self.state.status = ConnectivityStatus.DEGRADED
                        if old_status != ConnectivityStatus.DEGRADED:
                            self._notify_status_change(old_status, ConnectivityStatus.DEGRADED)
                        return ConnectivityStatus.DEGRADED
                    else:
                        return old_status

        except httpx.TimeoutException:
            old_status = self.state.status
            self.state.consecutive_failures += 1
            self.state.last_error = "Timeout"
            self.state.last_check = _utc_now()

            if self.state.consecutive_failures >= self.failure_threshold:
                self.state.status = ConnectivityStatus.OFFLINE
                if old_status != ConnectivityStatus.OFFLINE:
                    self._notify_status_change(old_status, ConnectivityStatus.OFFLINE)
                return ConnectivityStatus.OFFLINE
            else:
                return old_status

        except Exception as e:
            old_status = self.state.status
            self.state.consecutive_failures += 1
            self.state.last_error = str(e)
            self.state.last_check = _utc_now()

            if self.state.consecutive_failures >= self.failure_threshold:
                self.state.status = ConnectivityStatus.OFFLINE
                if old_status != ConnectivityStatus.OFFLINE:
                    self._notify_status_change(old_status, ConnectivityStatus.OFFLINE)
                return ConnectivityStatus.OFFLINE
            else:
                return old_status

    def get_status(self) -> ConnectivityStatus:
        """Get current connectivity status"""
        return self.state.status

    def is_online(self) -> bool:
        """Check if currently online"""
        return self.state.status == ConnectivityStatus.ONLINE

    def start_monitoring(self):
        """Start periodic connectivity monitoring"""
        if self._monitoring_task is not None:
            return

        self._stop_monitoring = False
        self._monitoring_task = asyncio.create_task(self._monitoring_loop())

    def stop_monitoring(self):
        """Stop periodic connectivity monitoring"""
        self._stop_monitoring = True
        if self._monitoring_task:
            self._monitoring_task.cancel()
            self._monitoring_task = None

    async def _monitoring_loop(self):
        """Periodic monitoring loop"""
        while not self._stop_monitoring:
            try:
                await self.check_connectivity()
                await asyncio.sleep(self.check_interval.total_seconds())
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in connectivity monitoring loop: {e}")
                await asyncio.sleep(self.check_interval.total_seconds())

    def _notify_status_change(
        self,
        old_status: ConnectivityStatus,
        new_status: ConnectivityStatus
    ):
        """Notify callbacks of status change"""
        for callback in self._status_callbacks:
            try:
                callback(old_status, new_status)
            except Exception as e:
                logger.error(f"Error in status change callback: {e}")


class OfflineModeManager:
    """Manages offline mode and graceful degradation"""

    def __init__(
        self,
        connectivity_monitor: ConnectivityMonitor,
    ):
        """
        Initialize offline mode manager

        Args:
            connectivity_monitor: ConnectivityMonitor instance
        """
        self.connectivity_monitor = connectivity_monitor
        self._pending_sync_tasks: List[Callable] = []

        self.connectivity_monitor.add_status_callback(self._on_connectivity_change)

    def _on_connectivity_change(
        self,
        old_status: ConnectivityStatus,
        new_status: ConnectivityStatus
    ):
        """Handle connectivity status change"""
        if new_status == ConnectivityStatus.ONLINE and old_status != ConnectivityStatus.ONLINE:
            logger.info("Connectivity restored, triggering pending syncs")
            asyncio.create_task(self._sync_pending_changes())

    async def _sync_pending_changes(self):
        """Sync pending changes when connectivity is restored"""
        tasks = self._pending_sync_tasks.copy()
        self._pending_sync_tasks.clear()

        for task in tasks:
            try:
                if asyncio.iscoroutinefunction(task):
                    await task()
                elif callable(task):
                    task()
            except Exception as e:
                logger.error(f"Error syncing pending change: {e}")

    def is_offline(self) -> bool:
        """Check if currently in offline mode"""
        return not self.connectivity_monitor.is_online()

    def can_perform_operation(self, operation: str) -> bool:
        """
        Check if operation can be performed in current mode

        Args:
            operation: Operation name (e.g., "fetch_asset", "sync_instance")

        Returns:
            True if operation can be performed
        """
        if self.connectivity_monitor.is_online():
            return True

        offline_capable_operations = [
            "load_cached_asset",
            "create_local_instance",
            "edit_local_instance",
        ]

        return operation in offline_capable_operations

    def queue_sync_task(self, task: Callable):
        """
        Queue sync task for execution when online

        Args:
            task: Async or sync callable to execute
        """
        if self.connectivity_monitor.is_online():
            try:
                if asyncio.iscoroutinefunction(task):
                    asyncio.create_task(task())
                elif callable(task):
                    task()
            except Exception as e:
                logger.error(f"Error executing sync task: {e}")
        else:
            self._pending_sync_tasks.append(task)
            logger.debug(f"Queued sync task for execution when online")

    def get_offline_capabilities(self) -> dict:
        """
        Get capabilities available in offline mode

        Returns:
            Dictionary of offline capabilities
        """
        return {
            "execute_cached_flow": True,
            "execute_cached_playbook": True,
            "create_brand_instance": True,
            "edit_brand_instance": True,
            "version_check": False,
            "fetch_new_assets": False,
            "license_validation": "grace_period",
            "usage_statistics": "local_only",
        }

