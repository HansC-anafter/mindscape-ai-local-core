"""
Runtime Discovery Service

Provides logic to scan local directories and automatically identify
workflow runtime configurations (e.g., ComfyUI).
"""

import os
import yaml
import socket
import logging
from typing import Optional, Dict, Any, List
from pydantic import BaseModel

logger = logging.getLogger(__name__)


class DiscoveryResult(BaseModel):
    """Result of a runtime discovery scan"""

    is_valid: bool
    runtime_type: str
    name: str
    description: Optional[str] = None
    config_url: Optional[str] = None
    extra_metadata: Dict[str, Any] = {}
    error: Optional[str] = None


class RuntimeDiscoveryService:
    """Service to discover and configure workflow runtimes"""

    def scan_folder(self, path: str, runtime_type: str = "comfyui") -> DiscoveryResult:
        """
        Scan a folder to identify a runtime environment.
        """
        path = os.path.expanduser(path)
        if not os.path.exists(path):
            return DiscoveryResult(
                is_valid=False,
                runtime_type=runtime_type,
                name="",
                error="Path does not exist",
            )

        if runtime_type.lower() == "comfyui":
            return self._scan_comfyui(path)

        return DiscoveryResult(
            is_valid=False,
            runtime_type=runtime_type,
            name="",
            error=f"Unsupported runtime type: {runtime_type}",
        )

    def _scan_comfyui(self, path: str) -> DiscoveryResult:
        """
        Identify ComfyUI runtime from directory.
        """
        # 1. Base check: main.py and comfy directory
        main_py = os.path.join(path, "main.py")
        comfy_dir = os.path.join(path, "comfy")

        if not (os.path.isfile(main_py) and os.path.isdir(comfy_dir)):
            return DiscoveryResult(
                is_valid=False,
                runtime_type="comfyui",
                name="",
                error="Selected folder does not look like a ComfyUI installation (missing main.py or comfy/ directory)",
            )

        # 2. Extract metadata
        name = os.path.basename(path) or "ComfyUI"
        extra_metadata = {"install_path": path, "has_extra_model_paths": False}

        # 3. Check for extra_model_paths.yaml
        extra_paths_file = os.path.join(path, "extra_model_paths.yaml")
        if os.path.isfile(extra_paths_file):
            try:
                with open(extra_paths_file, "r") as f:
                    extra_paths = yaml.safe_load(f)
                    extra_metadata["extra_model_paths"] = extra_paths
                    extra_metadata["has_extra_model_paths"] = True
            except Exception as e:
                logger.warning(f"Failed to read extra_model_paths.yaml: {e}")

        # 4. Port detection (default 8188)
        port = 8188
        config_url = f"http://localhost:{port}"

        # Try to see if something is listening
        if self._is_port_open("localhost", port):
            extra_metadata["port_status"] = "active"
        else:
            extra_metadata["port_status"] = "inactive"

        return DiscoveryResult(
            is_valid=True,
            runtime_type="comfyui",
            name=f"ComfyUI ({name})",
            description=f"Auto-discovered ComfyUI at {path}",
            config_url=config_url,
            extra_metadata=extra_metadata,
        )

    def _is_port_open(self, host: str, port: int) -> bool:
        """Check if a port is open on a host"""
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.settimeout(0.5)
                return s.connect_ex((host, port)) == 0
        except:
            return False
