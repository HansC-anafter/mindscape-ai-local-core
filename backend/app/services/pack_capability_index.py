"""
Pack Capability Index — file_type → pack_code lookup

Reads installed manifest.yaml files to build an in-memory index
mapping file types (video, audio, image, document, etc.) to
the pack codes that declare support for them.
"""

import logging
import os
from pathlib import Path
from typing import Dict, List
from app.services.runtime_pack_hygiene import is_ignored_runtime_pack_dir

logger = logging.getLogger(__name__)


class PackCapabilityIndex:
    """Query installed packs by file type capability."""

    def __init__(self):
        self._index: Dict[str, List[str]] = {}
        self._loaded = False

    def _load(self):
        """Load file_types from installed capability manifests."""
        if self._loaded:
            return
        self._loaded = True

        try:
            import yaml
        except ImportError:
            logger.warning("PyYAML not available, PackCapabilityIndex disabled")
            return

        caps_dir = None

        # Primary: backend/app/capabilities (where RuntimeAssetsInstaller writes)
        # In container: /app/backend/app/capabilities
        app_dir = os.getenv("APP_DIR", "/app")
        primary = Path(app_dir) / "backend" / "app" / "capabilities"
        if primary.exists():
            caps_dir = primary
        else:
            # Fallback: try relative to cwd
            relative = Path("backend/app/capabilities")
            if relative.exists():
                caps_dir = relative
            else:
                # Legacy: DATA_DIR/capabilities (if ever used)
                legacy = Path(os.getenv("DATA_DIR", "data")) / "capabilities"
                if legacy.exists():
                    caps_dir = legacy

        if not caps_dir or not caps_dir.exists():
            logger.debug(f"Capabilities directory not found (tried {primary})")
            return

        for manifest_path in caps_dir.glob("*/manifest.yaml"):
            pack_code = manifest_path.parent.name
            if is_ignored_runtime_pack_dir(pack_code):
                continue
            try:
                manifest = yaml.safe_load(manifest_path.read_text(encoding="utf-8"))
                if not manifest:
                    continue
                file_types = manifest.get("file_types", [])
                if not isinstance(file_types, list):
                    continue
                for ft in file_types:
                    if isinstance(ft, str):
                        self._index.setdefault(ft, []).append(pack_code)
            except Exception as e:
                logger.warning(f"Failed to read manifest for {pack_code}: {e}")

        if self._index:
            logger.info(
                f"PackCapabilityIndex loaded: "
                f"{sum(len(v) for v in self._index.values())} mappings "
                f"across {len(self._index)} file types"
            )
        else:
            logger.debug("PackCapabilityIndex: no file_types found in manifests")

    def get_packs_for_file_type(self, detected_type: str) -> List[str]:
        """Return pack codes that can handle this file type."""
        self._load()
        return list(self._index.get(detected_type, []))

    def get_all_file_types(self) -> List[str]:
        """Return all known file types."""
        self._load()
        return sorted(self._index.keys())

    def get_recommended_packs(self, detected_types: List[str]) -> List[str]:
        """Return union of pack codes for multiple file types."""
        self._load()
        result = set()
        for dt in detected_types:
            result.update(self._index.get(dt, []))
        return sorted(result)
