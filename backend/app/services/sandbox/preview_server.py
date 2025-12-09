"""
Preview server for dynamic web page sandboxes

Provides development mode preview server for React components and web pages.
Uses centralized PortManager for port allocation.
"""

import asyncio
import logging
from pathlib import Path
from typing import Optional, Dict, Any
import subprocess
import signal
import os

from backend.app.services.sandbox.port_manager import port_manager

logger = logging.getLogger(__name__)


class SandboxPreviewServer:
    """
    Preview server for sandbox web pages

    Provides development mode server for real-time preview of React components.
    Uses centralized PortManager for port allocation.
    """

    def __init__(self, sandbox_id: str, sandbox_path: Path, preferred_port: Optional[int] = None):
        """
        Initialize preview server

        Args:
            sandbox_id: Unique sandbox identifier (for port allocation)
            sandbox_path: Path to sandbox directory
            preferred_port: Optional preferred port (uses PortManager range if not specified)
        """
        self.sandbox_id = sandbox_id
        self.sandbox_path = sandbox_path
        self.preferred_port = preferred_port
        self.actual_port: Optional[int] = None
        self.process: Optional[subprocess.Popen] = None
        self.is_running = False
        self.error_message: Optional[str] = None

    async def start(self) -> Dict[str, Any]:
        """
        Start preview server

        Uses PortManager for centralized port allocation.

        Returns:
            Dictionary with status information:
            - success: True if started successfully
            - port: Actual port number used
            - url: Preview server URL
            - error: Error message if failed
            - port_conflict: True if preferred port was not available
        """
        if self.is_running:
            logger.warning("Preview server is already running")
            return {
                "success": True,
                "port": self.actual_port,
                "url": self.get_preview_url(),
                "error": None,
                "port_conflict": False,
            }

        try:
            package_json = self.sandbox_path / "package.json"
            if not package_json.exists():
                error_msg = "package.json not found, cannot start preview server"
                logger.warning(error_msg)
                self.error_message = error_msg
                return {
                    "success": False,
                    "port": None,
                    "url": None,
                    "error": error_msg,
                    "port_conflict": False,
                }

            # Allocate port via PortManager
            allocated_port = port_manager.allocate(self.sandbox_id, self.preferred_port)
            if not allocated_port:
                error_msg = f"No available ports in range {port_manager.port_start}-{port_manager.port_end}"
                logger.error(error_msg)
                self.error_message = error_msg
                return {
                    "success": False,
                    "port": None,
                    "url": None,
                    "error": error_msg,
                    "port_conflict": True,
                }
            
            port_conflict = self.preferred_port and allocated_port != self.preferred_port

            # Check if node_modules exists, install if not
            node_modules = self.sandbox_path / "node_modules"
            if not node_modules.exists():
                logger.info(f"Installing dependencies in {self.sandbox_path}...")
                install_result = subprocess.run(
                    ["npm", "install"],
                    cwd=str(self.sandbox_path),
                    capture_output=True,
                    timeout=120  # 2 minute timeout for npm install
                )
                if install_result.returncode != 0:
                    port_manager.release(self.sandbox_id)  # Release on failure
                    error_output = install_result.stderr.decode('utf-8', errors='ignore')
                    error_msg = f"npm install failed: {error_output[:200]}"
                    logger.error(error_msg)
                    self.error_message = error_msg
                    return {
                        "success": False,
                        "port": None,
                        "url": None,
                        "error": error_msg,
                        "port_conflict": False,
                    }
                logger.info("Dependencies installed successfully")

            env = os.environ.copy()
            env["PORT"] = str(allocated_port)

            self.process = subprocess.Popen(
                ["npm", "run", "dev"],
                cwd=str(self.sandbox_path),
                env=env,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                start_new_session=True
            )

            # Wait longer for Next.js to start (especially first time)
            await asyncio.sleep(5)

            if self.process.poll() is None:
                self.is_running = True
                self.actual_port = allocated_port
                logger.info(f"Preview server started on port {allocated_port}")
                if port_conflict:
                    logger.info(f"Note: Preferred port {self.preferred_port} was in use, using port {allocated_port}")
                return {
                    "success": True,
                    "port": allocated_port,
                    "url": f"http://localhost:{allocated_port}",
                    "error": None,
                    "port_conflict": port_conflict,
                }
            else:
                port_manager.release(self.sandbox_id)  # Release on failure
                stdout, stderr = self.process.communicate()
                error_output = stderr.decode('utf-8', errors='ignore') if stderr else ""
                error_msg = f"Preview server failed to start: {error_output[:200]}"
                logger.error(error_msg)
                self.error_message = error_msg
                return {
                    "success": False,
                    "port": None,
                    "url": None,
                    "error": error_msg,
                    "port_conflict": port_conflict,
                }

        except Exception as e:
            error_msg = f"Failed to start preview server: {str(e)}"
            logger.error(error_msg)
            self.error_message = error_msg
            return {
                "success": False,
                "port": None,
                "url": None,
                "error": error_msg,
                "port_conflict": False,
            }

    async def stop(self) -> bool:
        """
        Stop preview server and release port allocation.

        Returns:
            True if stopped successfully, False otherwise
        """
        if not self.is_running or not self.process:
            # Still release port even if not running
            port_manager.release(self.sandbox_id)
            return True

        try:
            self.process.terminate()
            try:
                self.process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.process.kill()
                self.process.wait()

            self.is_running = False
            self.actual_port = None
            
            # Release port allocation
            port_manager.release(self.sandbox_id)
            
            logger.info(f"Preview server stopped for sandbox {self.sandbox_id}")
            return True

        except Exception as e:
            logger.error(f"Failed to stop preview server: {e}")
            # Still try to release port
            port_manager.release(self.sandbox_id)
            return False

    def get_preview_url(self) -> str:
        """
        Get preview server URL

        Returns:
            Preview server URL (uses actual_port if available, otherwise port)
        """
        port = self.actual_port if self.actual_port else self.port
        return f"http://localhost:{port}"

    async def is_healthy(self) -> bool:
        """
        Check if preview server is healthy

        Returns:
            True if server is responding, False otherwise
        """
        if not self.is_running or not self.process:
            return False

        if self.process.poll() is not None:
            self.is_running = False
            return False

        try:
            import aiohttp
            async with aiohttp.ClientSession() as session:
                async with session.get(self.get_preview_url(), timeout=2) as response:
                    return response.status == 200
        except Exception:
            return False

