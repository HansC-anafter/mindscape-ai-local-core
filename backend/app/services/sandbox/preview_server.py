"""
Preview server for dynamic web page sandboxes

Provides development mode preview server for React components and web pages.
Handles port conflicts by automatically finding available ports.
"""

import asyncio
import logging
import socket
from pathlib import Path
from typing import Optional, Dict, Any
import subprocess
import signal
import os

logger = logging.getLogger(__name__)


class SandboxPreviewServer:
    """
    Preview server for sandbox web pages

    Provides development mode server for real-time preview of React components.
    """

    def __init__(self, sandbox_path: Path, port: int = 3000):
        """
        Initialize preview server

        Args:
            sandbox_path: Path to sandbox directory
            port: Port number for preview server (will auto-find available port if conflict)
        """
        self.sandbox_path = sandbox_path
        self.port = port
        self.actual_port: Optional[int] = None
        self.process: Optional[subprocess.Popen] = None
        self.is_running = False
        self.error_message: Optional[str] = None

    @staticmethod
    def _is_port_available(port: int) -> bool:
        """
        Check if a port is available

        Args:
            port: Port number to check

        Returns:
            True if port is available, False otherwise
        """
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.settimeout(1)
                result = s.connect_ex(('localhost', port))
                return result != 0
        except Exception:
            return False

    @staticmethod
    def _find_available_port(start_port: int, max_attempts: int = 10) -> Optional[int]:
        """
        Find an available port starting from start_port

        Args:
            start_port: Starting port number
            max_attempts: Maximum number of ports to try

        Returns:
            Available port number or None if not found
        """
        for i in range(max_attempts):
            port = start_port + i
            if SandboxPreviewServer._is_port_available(port):
                return port
        return None

    async def start(self) -> Dict[str, Any]:
        """
        Start preview server

        Automatically handles port conflicts by finding an available port.

        Returns:
            Dictionary with status information:
            - success: True if started successfully
            - port: Actual port number used
            - url: Preview server URL
            - error: Error message if failed
            - port_conflict: True if original port was in use
        """
        if self.is_running:
            logger.warning("Preview server is already running")
            return {
                "success": True,
                "port": self.actual_port or self.port,
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

            port_conflict = False
            actual_port = self.port

            if not self._is_port_available(self.port):
                logger.warning(f"Port {self.port} is in use, finding available port...")
                port_conflict = True
                available_port = self._find_available_port(self.port)
                if available_port:
                    actual_port = available_port
                    logger.info(f"Found available port: {actual_port}")
                else:
                    error_msg = f"Could not find available port starting from {self.port}"
                    logger.error(error_msg)
                    self.error_message = error_msg
                    return {
                        "success": False,
                        "port": None,
                        "url": None,
                        "error": error_msg,
                        "port_conflict": True,
                    }

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
            env["PORT"] = str(actual_port)

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
                self.actual_port = actual_port
                logger.info(f"Preview server started on port {actual_port}")
                if port_conflict:
                    logger.info(f"Note: Original port {self.port} was in use, using port {actual_port} instead")
                return {
                    "success": True,
                    "port": actual_port,
                    "url": f"http://localhost:{actual_port}",
                    "error": None,
                    "port_conflict": port_conflict,
                }
            else:
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
        Stop preview server

        Returns:
            True if stopped successfully, False otherwise
        """
        if not self.is_running or not self.process:
            return True

        try:
            self.process.terminate()
            try:
                self.process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.process.kill()
                self.process.wait()

            self.is_running = False
            logger.info("Preview server stopped")
            return True

        except Exception as e:
            logger.error(f"Failed to stop preview server: {e}")
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

