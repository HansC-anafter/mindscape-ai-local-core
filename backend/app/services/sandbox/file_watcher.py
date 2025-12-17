"""
File watcher for workspace-sandbox automatic sync

Provides file system watching and incremental sync for real-time preview.
"""
import asyncio
import logging
from pathlib import Path
from typing import Optional, Dict, Any, Callable, Set
import time

try:
    from watchdog.observers import Observer
    from watchdog.events import FileSystemEventHandler, FileSystemEvent
    WATCHDOG_AVAILABLE = True
except ImportError:
    WATCHDOG_AVAILABLE = False
    Observer = None
    FileSystemEventHandler = None

from backend.app.services.sandbox.workspace_sync import WorkspaceSandboxSync

logger = logging.getLogger(__name__)


class WorkspaceFileHandler(FileSystemEventHandler):
    """File system event handler for workspace changes"""

    def __init__(
        self,
        workspace_path: Path,
        sync_callback: Callable[[str, str], None],
        sync_directories: Optional[list] = None,
        debounce_seconds: float = 0.5
    ):
        """
        Initialize file handler.

        Args:
            workspace_path: Workspace directory path
            sync_callback: Callback function (file_path, event_type) -> None
            sync_directories: Optional list of directories to watch
            debounce_seconds: Debounce delay in seconds
        """
        self.workspace_path = workspace_path
        self.sync_callback = sync_callback
        self.sync_directories = sync_directories or []
        self.debounce_seconds = debounce_seconds

        self.pending_changes: Dict[str, float] = {}
        self.debounce_task: Optional[asyncio.Task] = None

    def _should_watch(self, file_path: str) -> bool:
        """Check if file should be watched"""
        if not self.sync_directories:
            return True

        for dir_name in self.sync_directories:
            if file_path.startswith(dir_name + "/") or file_path.startswith(dir_name + "\\"):
                return True
            if file_path == dir_name or file_path.startswith(dir_name):
                return True

        return False

    def _get_relative_path(self, src_path: str) -> Optional[str]:
        """Get relative path from workspace"""
        try:
            full_path = Path(src_path)
            if full_path.is_absolute():
                try:
                    return str(full_path.relative_to(self.workspace_path))
                except ValueError:
                    return None
            return src_path
        except Exception:
            return None

    def on_modified(self, event: FileSystemEvent):
        """Handle file modification"""
        if event.is_directory:
            return

        rel_path = self._get_relative_path(event.src_path)
        if not rel_path or not self._should_watch(rel_path):
            return

        self._schedule_sync(rel_path, "modified")

    def on_created(self, event: FileSystemEvent):
        """Handle file creation"""
        if event.is_directory:
            return

        rel_path = self._get_relative_path(event.src_path)
        if not rel_path or not self._should_watch(rel_path):
            return

        self._schedule_sync(rel_path, "created")

    def on_deleted(self, event: FileSystemEvent):
        """Handle file deletion"""
        if event.is_directory:
            return

        rel_path = self._get_relative_path(event.src_path)
        if not rel_path or not self._should_watch(rel_path):
            return

        self._schedule_sync(rel_path, "deleted")

    def _schedule_sync(self, file_path: str, event_type: str):
        """Schedule sync with debouncing"""
        current_time = time.time()
        self.pending_changes[file_path] = current_time

        if self.debounce_task and not self.debounce_task.done():
            return

        async def debounced_sync():
            await asyncio.sleep(self.debounce_seconds)
            now = time.time()

            files_to_sync = [
                path for path, timestamp in self.pending_changes.items()
                if now - timestamp >= self.debounce_seconds
            ]

            if files_to_sync:
                for path in files_to_sync:
                    self.sync_callback(path, event_type)
                    self.pending_changes.pop(path, None)

        self.debounce_task = asyncio.create_task(debounced_sync())


class WorkspaceFileWatcher:
    """
    File watcher for workspace-sandbox automatic sync.

    Watches workspace files and automatically syncs changes to sandbox.
    """

    def __init__(
        self,
        workspace_id: str,
        sandbox_id: str,
        sync_service: WorkspaceSandboxSync,
        sync_directories: Optional[list] = None
    ):
        """
        Initialize file watcher.

        Args:
            workspace_id: Workspace identifier
            sandbox_id: Sandbox identifier
            sync_service: WorkspaceSandboxSync service instance
            sync_directories: Optional list of directories to watch
        """
        if not WATCHDOG_AVAILABLE:
            raise ImportError("watchdog package is required for file watching")

        self.workspace_id = workspace_id
        self.sandbox_id = sandbox_id
        self.sync_service = sync_service
        self.sync_directories = sync_directories

        self.workspace_path = sync_service.get_workspace_path(workspace_id)
        self.observer: Optional[Observer] = None
        self.handler: Optional[WorkspaceFileHandler] = None
        self.is_watching = False

    async def start(self) -> bool:
        """
        Start watching workspace files.

        Returns:
            True if started successfully
        """
        if self.is_watching:
            logger.warning(f"File watcher already running for sandbox {self.sandbox_id}")
            return True

        if not self.workspace_path.exists():
            logger.error(f"Workspace path does not exist: {self.workspace_path}")
            return False

        try:
            async def sync_callback(file_path: str, event_type: str):
                """Callback for file changes"""
                try:
                    logger.debug(f"File {event_type}: {file_path}, syncing to sandbox...")
                    await self._sync_file(file_path, event_type)
                except Exception as e:
                    logger.error(f"Failed to sync {file_path}: {e}")

            self.handler = WorkspaceFileHandler(
                workspace_path=self.workspace_path,
                sync_callback=sync_callback,
                sync_directories=self.sync_directories,
                debounce_seconds=0.5
            )

            self.observer = Observer()
            self.observer.schedule(
                self.handler,
                str(self.workspace_path),
                recursive=True
            )
            self.observer.start()
            self.is_watching = True

            logger.info(f"Started file watcher for sandbox {self.sandbox_id}")
            return True

        except Exception as e:
            logger.error(f"Failed to start file watcher: {e}")
            return False

    def stop(self):
        """Stop watching files"""
        if not self.is_watching:
            return

        if self.observer:
            self.observer.stop()
            self.observer.join(timeout=5)
            self.observer = None

        self.handler = None
        self.is_watching = False
        logger.info(f"Stopped file watcher for sandbox {self.sandbox_id}")

    async def _sync_file(self, file_path: str, event_type: str):
        """
        Sync single file to sandbox.

        Args:
            file_path: Relative file path
            event_type: Event type (created, modified, deleted)
        """
        try:
            sandbox = await self.sync_service.sandbox_manager.get_sandbox(
                self.sandbox_id, self.workspace_id
            )
            if not sandbox:
                logger.error(f"Sandbox not found: {self.sandbox_id}")
                return

            source_file = self.workspace_path / file_path

            if event_type == "deleted":
                await sandbox.delete_file(file_path)
                logger.debug(f"Deleted from sandbox: {file_path}")
            else:
                if source_file.exists():
                    content = source_file.read_text(encoding="utf-8")
                    await sandbox.write_file(file_path, content)
                    logger.debug(f"Synced to sandbox: {file_path}")

        except Exception as e:
            logger.error(f"Failed to sync file {file_path}: {e}")

    def is_active(self) -> bool:
        """Check if watcher is active"""
        return self.is_watching and self.observer and self.observer.is_alive()


# Global watcher registry
_watchers: Dict[str, WorkspaceFileWatcher] = {}


def get_watcher_key(workspace_id: str, sandbox_id: str) -> str:
    """Get watcher registry key"""
    return f"{workspace_id}:{sandbox_id}"


async def start_watching(
    workspace_id: str,
    sandbox_id: str,
    sync_service: WorkspaceSandboxSync,
    sync_directories: Optional[list] = None
) -> bool:
    """
    Start watching workspace files for sandbox.

    Args:
        workspace_id: Workspace identifier
        sandbox_id: Sandbox identifier
        sync_service: WorkspaceSandboxSync service instance
        sync_directories: Optional list of directories to watch

    Returns:
        True if started successfully
    """
    if not WATCHDOG_AVAILABLE:
        logger.warning("watchdog package not available, file watching disabled")
        return False

    key = get_watcher_key(workspace_id, sandbox_id)

    if key in _watchers:
        watcher = _watchers[key]
        if watcher.is_active():
            logger.debug(f"Watcher already active for {key}")
            return True
        else:
            del _watchers[key]

    watcher = WorkspaceFileWatcher(
        workspace_id=workspace_id,
        sandbox_id=sandbox_id,
        sync_service=sync_service,
        sync_directories=sync_directories
    )

    success = await watcher.start()
    if success:
        _watchers[key] = watcher

    return success


def stop_watching(workspace_id: str, sandbox_id: str):
    """
    Stop watching workspace files for sandbox.

    Args:
        workspace_id: Workspace identifier
        sandbox_id: Sandbox identifier
    """
    key = get_watcher_key(workspace_id, sandbox_id)

    if key in _watchers:
        watcher = _watchers[key]
        watcher.stop()
        del _watchers[key]
        logger.info(f"Stopped watching for {key}")


def stop_all_watchers():
    """Stop all active watchers"""
    for watcher in list(_watchers.values()):
        watcher.stop()
    _watchers.clear()
    logger.info("Stopped all file watchers")

