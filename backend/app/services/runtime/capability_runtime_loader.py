"""
Capability Runtime Loader - Discovers and loads runtime providers from capability packs

Scans capability packs for runtime providers (type: system_runtime) and
dynamically loads them into RuntimeFactory.
"""

import logging
import yaml
import importlib
import sys
from pathlib import Path
from typing import List, Dict, Any, Optional

from backend.app.core.runtime_port import RuntimePort

logger = logging.getLogger(__name__)


class CapabilityRuntimeLoader:
    """Loads runtime providers from capability packs"""

    def __init__(self, capabilities_dirs: Optional[List[Path]] = None):
        """
        Initialize CapabilityRuntimeLoader

        Args:
            capabilities_dirs: List of directories to scan for capability packs
                              (default: tries to find from environment or common locations)
        """
        self.capabilities_dirs = capabilities_dirs or self._find_capabilities_dirs()
        self.loaded_runtimes: Dict[str, RuntimePort] = {}

    def _find_capabilities_dirs(self) -> List[Path]:
        """
        Find capability directories to scan

        Returns:
            List of Path objects pointing to capability directories
        """
        dirs = []

        # Try environment variable
        import os
        env_dir = os.getenv("MINDSCAPE_CAPABILITIES_DIR")
        if env_dir:
            dirs.append(Path(env_dir))

        # Try common locations relative to workspace
        # Assume capabilities are in mindscape-ai-cloud/capabilities
        workspace_root = Path(__file__).parent.parent.parent.parent.parent
        cloud_capabilities = workspace_root / "mindscape-ai-cloud" / "capabilities"
        if cloud_capabilities.exists():
            dirs.append(cloud_capabilities)

        # Try relative path from local-core
        local_core_dir = Path(__file__).parent.parent.parent.parent
        relative_capabilities = local_core_dir.parent / "mindscape-ai-cloud" / "capabilities"
        if relative_capabilities.exists():
            dirs.append(relative_capabilities)

        return dirs

    def scan_capability_packs(self) -> List[Dict[str, Any]]:
        """
        Scan capability directories for runtime providers

        Returns:
            List of capability pack info dicts with type: system_runtime
        """
        runtime_packs = []

        for capabilities_dir in self.capabilities_dirs:
            if not capabilities_dir.exists():
                logger.debug(f"Capabilities directory does not exist: {capabilities_dir}")
                continue

            logger.debug(f"Scanning capabilities directory: {capabilities_dir}")

            # Scan each subdirectory
            for pack_dir in capabilities_dir.iterdir():
                if not pack_dir.is_dir():
                    continue

                manifest_path = pack_dir / "manifest.yaml"
                if not manifest_path.exists():
                    continue

                try:
                    with open(manifest_path, 'r', encoding='utf-8') as f:
                        manifest = yaml.safe_load(f)

                    # Check if this is a runtime provider
                    pack_type = manifest.get("type")
                    if pack_type == "system_runtime":
                        runtime_packs.append({
                            "code": manifest.get("code"),
                            "display_name": manifest.get("display_name"),
                            "version": manifest.get("version"),
                            "path": pack_dir,
                            "manifest": manifest
                        })
                        logger.info(f"Found runtime provider: {manifest.get('code')} at {pack_dir}")

                except Exception as e:
                    logger.warning(f"Failed to load manifest from {manifest_path}: {e}")

        return runtime_packs

    def load_runtime_provider(
        self,
        pack_info: Dict[str, Any]
    ) -> Optional[RuntimePort]:
        """
        Load a runtime provider from capability pack

        Args:
            pack_info: Capability pack info dict from scan_capability_packs()

        Returns:
            RuntimePort instance or None if loading failed
        """
        pack_code = pack_info["code"]
        pack_path = pack_info["path"]
        manifest = pack_info["manifest"]

        # Get runtime provider class from manifest
        runtime_provider_config = manifest.get("runtime_provider")
        if not runtime_provider_config:
            logger.warning(f"No runtime_provider config in manifest for {pack_code}")
            return None

        class_path = runtime_provider_config.get("class")
        if not class_path:
            logger.warning(f"No class specified in runtime_provider for {pack_code}")
            return None

        try:
            # Parse class path (e.g., "langgraph_runtime.LangGraphRuntime")
            module_name, class_name = class_path.rsplit(".", 1)

            # Add pack directory to Python path temporarily
            pack_dir_str = str(pack_path)
            if pack_dir_str not in sys.path:
                sys.path.insert(0, pack_dir_str)

            try:
                # Import module
                module = importlib.import_module(module_name)
                runtime_class = getattr(module, class_name)

                # Instantiate runtime
                runtime = runtime_class(store=None)  # Store can be passed if needed

                if not isinstance(runtime, RuntimePort):
                    logger.error(
                        f"Class {class_path} does not implement RuntimePort interface"
                    )
                    return None

                logger.info(f"Successfully loaded runtime provider: {pack_code} ({runtime.name})")
                return runtime

            finally:
                # Remove from path
                if pack_dir_str in sys.path:
                    sys.path.remove(pack_dir_str)

        except Exception as e:
            logger.error(
                f"Failed to load runtime provider {pack_code} from {class_path}: {e}",
                exc_info=True
            )
            return None

    def load_all_runtime_providers(self) -> List[RuntimePort]:
        """
        Scan and load all runtime providers

        Returns:
            List of loaded RuntimePort instances
        """
        runtime_packs = self.scan_capability_packs()
        loaded_runtimes = []

        for pack_info in runtime_packs:
            runtime = self.load_runtime_provider(pack_info)
            if runtime:
                loaded_runtimes.append(runtime)
                self.loaded_runtimes[pack_info["code"]] = runtime

        return loaded_runtimes
