"""
Cache Store
Manages local cache for cloud-synced assets (flows, playbooks, schemas, etc.)
"""

import json
import logging
import hashlib
from pathlib import Path
from datetime import datetime, timedelta, timezone


def _utc_now():
    """Return timezone-aware UTC now."""
    return datetime.now(timezone.utc)
from typing import Optional, Dict, Any, List
from enum import Enum

logger = logging.getLogger(__name__)


class CacheLifecycle(Enum):
    """Cache lifecycle status"""
    VALID = "valid"
    STALE = "stale"
    EXPIRED = "expired"
    INVALID = "invalid"


class CacheTTL:
    """Cache TTL configuration"""

    DEFAULT_TTL = {
        "capability": timedelta(days=7),
        "flow": timedelta(days=7),
        "playbook": timedelta(days=7),
        "schema": timedelta(days=30),
        "prompt": timedelta(days=1),
        "license": timedelta(days=1),
    }

    GRACE_PERIOD = {
        "license": timedelta(days=3),
    }

    STALE_WHILE_REVALIDATE = timedelta(hours=1)


class CacheStore:
    """Manages local cache for cloud-synced assets"""

    def __init__(self, cache_root: Optional[Path] = None):
        """
        Initialize cache store

        Args:
            cache_root: Root directory for cache (defaults to ~/.mindscape/cache)
        """
        if cache_root is None:
            cache_root = Path.home() / ".mindscape" / "cache"

        self.cache_root = Path(cache_root)
        self.manifest_path = self.cache_root / "manifest.json"
        self._manifest: Optional[Dict[str, Any]] = None

        self._init_cache_structure()

    def _init_cache_structure(self):
        """Initialize cache directory structure"""
        directories = [
            self.cache_root,
            self.cache_root / "capabilities",
            self.cache_root / "flows",
            self.cache_root / "playbooks",
            self.cache_root / "schemas",
            self.cache_root / "prompts",
            self.cache_root / "license",
        ]

        for directory in directories:
            directory.mkdir(parents=True, exist_ok=True)

        if not self.manifest_path.exists():
            self._create_manifest()

    def _create_manifest(self):
        """Create initial manifest file"""
        manifest = {
            "version": "1.0.0",
            "last_sync": None,
            "device_id": None,
            "assets": {},
            "instances": {},
            "license": None,
        }
        self._write_manifest(manifest)

    def _read_manifest(self) -> Dict[str, Any]:
        """Read manifest file"""
        if self._manifest is not None:
            return self._manifest

        if not self.manifest_path.exists():
            self._create_manifest()
            return self._read_manifest()

        try:
            with open(self.manifest_path, "r", encoding="utf-8") as f:
                self._manifest = json.load(f)
                return self._manifest
        except Exception as e:
            logger.error(f"Failed to read manifest: {e}")
            self._create_manifest()
            return self._read_manifest()

    def _write_manifest(self, manifest: Dict[str, Any]):
        """Write manifest file"""
        try:
            with open(self.manifest_path, "w", encoding="utf-8") as f:
                json.dump(manifest, f, indent=2, ensure_ascii=False)
            self._manifest = manifest
        except Exception as e:
            logger.error(f"Failed to write manifest: {e}")
            raise

    def get_manifest(self) -> Dict[str, Any]:
        """Get current manifest"""
        return self._read_manifest()

    def update_manifest(self, updates: Dict[str, Any]):
        """Update manifest with new values"""
        manifest = self._read_manifest()
        manifest.update(updates)
        self._write_manifest(manifest)

    def get_asset_path(self, asset_uri: str) -> Path:
        """
        Get local file path for an asset

        Args:
            asset_uri: Asset URI in format mindscape://{type}/{capability}/{id}@{version}

        Returns:
            Path to cached asset file
        """
        parts = asset_uri.replace("mindscape://", "").split("/")
        if len(parts) < 3:
            raise ValueError(f"Invalid asset URI: {asset_uri}")

        asset_type = parts[0]
        capability = parts[1]
        id_version = parts[2]

        if "@" in id_version:
            asset_id, version = id_version.split("@")
        else:
            asset_id = id_version
            version = "latest"

        type_dir = self.cache_root / f"{asset_type}s"
        capability_dir = type_dir / capability
        asset_dir = capability_dir / asset_id
        version_dir = asset_dir / version

        return version_dir

    def store_asset(
        self,
        asset_uri: str,
        content: bytes,
        checksum: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> Path:
        """
        Store asset in cache

        Args:
            asset_uri: Asset URI
            content: Asset content as bytes
            checksum: SHA256 checksum (optional, will be computed if not provided)
            metadata: Additional metadata

        Returns:
            Path to stored asset file
        """
        if checksum is None:
            checksum = f"sha256:{hashlib.sha256(content).hexdigest()}"

        asset_path = self.get_asset_path(asset_uri)
        asset_path.mkdir(parents=True, exist_ok=True)

        content_type = self._get_content_type(asset_uri)
        asset_file = asset_path / f"asset.{content_type}"

        with open(asset_file, "wb") as f:
            f.write(content)

        metadata_file = asset_path / "metadata.json"
        asset_metadata = {
            "uri": asset_uri,
            "checksum": checksum,
            "size_bytes": len(content),
            "cached_at": _utc_now().isoformat(),
            "expires_at": self._get_expires_at(asset_uri).isoformat(),
            "status": CacheLifecycle.VALID.value,
            **(metadata or {}),
        }

        with open(metadata_file, "w", encoding="utf-8") as f:
            json.dump(asset_metadata, f, indent=2, ensure_ascii=False)

        manifest = self._read_manifest()
        manifest["assets"][asset_uri] = {
            "path": str(asset_file.relative_to(self.cache_root)),
            "checksum": checksum,
            "cached_at": asset_metadata["cached_at"],
            "expires_at": asset_metadata["expires_at"],
            "size_bytes": len(content),
            "status": CacheLifecycle.VALID.value,
        }
        self._write_manifest(manifest)

        return asset_file

    def get_asset(self, asset_uri: str) -> Optional[bytes]:
        """
        Get asset from cache

        Args:
            asset_uri: Asset URI

        Returns:
            Asset content as bytes, or None if not found
        """
        asset_path = self.get_asset_path(asset_uri)
        content_type = self._get_content_type(asset_uri)
        asset_file = asset_path / f"asset.{content_type}"

        if not asset_file.exists():
            return None

        try:
            with open(asset_file, "rb") as f:
                return f.read()
        except Exception as e:
            logger.error(f"Failed to read asset {asset_uri}: {e}")
            return None

    def get_asset_metadata(self, asset_uri: str) -> Optional[Dict[str, Any]]:
        """Get asset metadata from cache"""
        asset_path = self.get_asset_path(asset_uri)
        metadata_file = asset_path / "metadata.json"

        if not metadata_file.exists():
            return None

        try:
            with open(metadata_file, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"Failed to read asset metadata {asset_uri}: {e}")
            return None

    def _get_content_type(self, asset_uri: str) -> str:
        """Get file extension based on asset type"""
        asset_type = asset_uri.split("/")[0].replace("mindscape://", "")
        type_map = {
            "flow": "yaml",
            "playbook": "md",
            "schema": "json",
            "capability": "yaml",
            "prompt": "txt",
        }
        return type_map.get(asset_type, "json")

    def _get_expires_at(self, asset_uri: str) -> datetime:
        """Get expiration time for asset based on type"""
        asset_type = asset_uri.split("/")[0].replace("mindscape://", "")
        ttl = CacheTTL.DEFAULT_TTL.get(asset_type, timedelta(days=7))
        return _utc_now() + ttl

    def clear_asset(self, asset_uri: str):
        """Remove asset from cache"""
        asset_path = self.get_asset_path(asset_uri)

        if asset_path.exists():
            import shutil
            shutil.rmtree(asset_path)

        manifest = self._read_manifest()
        if asset_uri in manifest["assets"]:
            del manifest["assets"][asset_uri]
            self._write_manifest(manifest)

    def clear_expired_assets(self) -> int:
        """
        Clear expired assets from cache

        Returns:
            Number of assets cleared
        """
        cleared = 0
        manifest = self._read_manifest()
        assets_to_remove = []

        for asset_uri, asset_info in manifest["assets"].items():
            expires_at_str = asset_info.get("expires_at")
            if not expires_at_str:
                continue

            try:
                expires_at = datetime.fromisoformat(expires_at_str)
                if _utc_now() > expires_at:
                    assets_to_remove.append(asset_uri)
            except Exception as e:
                logger.warning(f"Failed to parse expiration for {asset_uri}: {e}")
                assets_to_remove.append(asset_uri)

        for asset_uri in assets_to_remove:
            self.clear_asset(asset_uri)
            cleared += 1

        return cleared


class CacheLifecycleManager:
    """Manages cache lifecycle and status"""

    def __init__(self, cache_store: CacheStore):
        """
        Initialize lifecycle manager

        Args:
            cache_store: CacheStore instance
        """
        self.cache_store = cache_store

    def get_asset_status(self, asset_uri: str) -> CacheLifecycle:
        """
        Get lifecycle status of cached asset

        Args:
            asset_uri: Asset URI

        Returns:
            Cache lifecycle status
        """
        metadata = self.cache_store.get_asset_metadata(asset_uri)
        if not metadata:
            return CacheLifecycle.INVALID

        expires_at_str = metadata.get("expires_at")
        if not expires_at_str:
            return CacheLifecycle.INVALID

        try:
            expires_at = datetime.fromisoformat(expires_at_str)
            now = _utc_now()

            if now > expires_at + CacheTTL.STALE_WHILE_REVALIDATE:
                return CacheLifecycle.EXPIRED
            elif now > expires_at:
                return CacheLifecycle.STALE
            else:
                return CacheLifecycle.VALID
        except Exception as e:
            logger.warning(f"Failed to check asset status {asset_uri}: {e}")
            return CacheLifecycle.INVALID

    def is_asset_valid(self, asset_uri: str) -> bool:
        """Check if asset is valid (not expired)"""
        status = self.get_asset_status(asset_uri)
        return status in [CacheLifecycle.VALID, CacheLifecycle.STALE]

    def cleanup_expired(self) -> Dict[str, int]:
        """
        Clean up expired assets

        Returns:
            Dictionary with cleanup statistics
        """
        cleared = self.cache_store.clear_expired_assets()
        return {
            "cleared": cleared,
            "timestamp": _utc_now().isoformat(),
        }

