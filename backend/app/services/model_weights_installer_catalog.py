"""Model integrity, lookup, delete, and usage seam."""

import hashlib
import json
import logging
import shutil
from pathlib import Path
from typing import Dict, List, Optional

from .model_weights_installer_types import ModelInfo, ModelStatus

logger = logging.getLogger(f"{__package__}.model_weights_installer")


class ModelWeightsInstallerCatalogMixin:
    def _get_model_fingerprint(self, model_info: ModelInfo) -> str:
        """Generate a unique fingerprint for model de-duplication."""
        fingerprint_data = {
            "provider": model_info.provider.value,
            "repo_id": model_info.repo_id,
            "revision": model_info.revision,
            "files": sorted([f.filename for f in model_info.files]),
            "hashes": sorted(
                [f.expected_hash for f in model_info.files if f.expected_hash]
            ),
            "local_bundle": model_info.local_bundle or {},
        }
        data_str = json.dumps(fingerprint_data, sort_keys=True)
        return hashlib.sha256(data_str.encode()).hexdigest()[:16]

    def _verify_model_files(self, model_info: ModelInfo) -> bool:
        """Verify all model files against expected hashes."""
        if not model_info.local_path:
            return False

        for file_info in model_info.files:
            file_path = model_info.local_path / file_info.filename
            if not file_path.exists():
                return False

            if file_info.expected_hash and not self._is_placeholder_hash(
                file_info.expected_hash
            ):
                if ":" in file_info.expected_hash:
                    algo, expected = file_info.expected_hash.split(":", 1)
                else:
                    algo, expected = "sha256", file_info.expected_hash

                actual = self._compute_hash(file_path, algo)
                if actual != expected:
                    logger.warning(
                        f"Hash mismatch for {file_path}: expected {expected}, got {actual}"
                    )
                    file_info.is_verified = False
                    return False

            file_info.is_verified = True

        return True

    def _is_placeholder_hash(self, expected_hash: str) -> bool:
        normalized = str(expected_hash or "").strip().lower()
        if not normalized:
            return True
        if ":" in normalized:
            _, normalized = normalized.split(":", 1)
        return normalized.startswith("placeholder_hash_") or normalized in {
            "placeholder",
            "tbd",
            "todo",
        }

    def _compute_hash(self, file_path: Path, algorithm: str = "sha256") -> str:
        """Compute file hash."""
        hash_func = hashlib.new(algorithm)
        with open(file_path, "rb") as f:
            for chunk in iter(lambda: f.read(8192), b""):
                hash_func.update(chunk)
        return hash_func.hexdigest()

    def get_model_path(self, pack_code: str, model_id: str) -> Optional[Path]:
        """Get local path for a model (None if not downloaded)."""
        key = self._get_model_key(pack_code, model_id)
        model_info = self._models.get(key)
        if model_info and model_info.status in [
            ModelStatus.DOWNLOADED,
            ModelStatus.VERIFIED,
        ]:
            return model_info.local_path
        return None

    def list_models(self, pack_code: Optional[str] = None) -> List[ModelInfo]:
        """List all models defined in manifests."""
        if pack_code:
            return [
                info
                for key, info in self._models.items()
                if info.pack_code == pack_code
            ]
        return list(self._models.values())

    def get_model_info(self, pack_code: str, model_id: str) -> Optional[ModelInfo]:
        """Get model info by pack and model_id."""
        key = self._get_model_key(pack_code, model_id)
        return self._models.get(key)

    def verify_model(self, pack_code: str, model_id: str) -> bool:
        """Verify model integrity against expected hash."""
        key = self._get_model_key(pack_code, model_id)
        model_info = self._models.get(key)
        if not model_info:
            return False
        return self._verify_model_files(model_info)

    async def delete_model(self, pack_code: str, model_id: str) -> bool:
        """Delete a downloaded model to free space."""
        key = self._get_model_key(pack_code, model_id)
        model_info = self._models.get(key)
        if not model_info or not model_info.local_path:
            return False

        try:
            shutil.rmtree(model_info.local_path)
            model_info.local_path = None
            model_info.status = ModelStatus.NOT_DOWNLOADED
            for file_info in model_info.files:
                file_info.local_path = None
                file_info.is_downloaded = False
                file_info.is_verified = False
            self._save_state()
            return True
        except Exception as e:
            logger.error(f"Failed to delete model {model_id}: {e}")
            return False

    def get_disk_usage(self, pack_code: Optional[str] = None) -> Dict[str, int]:
        """
        Get disk usage for models (total or per-pack).
        For per-pack usage, we traverse the 'by_pack' view to count logical consumption.
        """
        usage = {}

        def get_path_size(path: Path) -> int:
            total = 0
            if path.exists():
                if path.is_symlink():
                    target = path.resolve()
                    if target.exists():
                        for entry in target.rglob("*"):
                            if entry.is_file():
                                total += entry.stat().st_size
                elif path.is_dir():
                    for entry in path.rglob("*"):
                        if entry.is_file():
                            total += entry.stat().st_size
            return total

        if pack_code:
            pack_total = 0
            for role_dir in self.cache_root.iterdir():
                if role_dir.is_dir() and role_dir.name in self.ROLE_MAP.values():
                    pack_view = role_dir / "by_pack" / pack_code
                    if pack_view.exists():
                        for model_entry in pack_view.iterdir():
                            pack_total += get_path_size(model_entry)
            usage[pack_code] = pack_total
        else:
            global_total = 0
            for role_dir in self.cache_root.iterdir():
                if role_dir.is_dir() and role_dir.name in self.ROLE_MAP.values():
                    store_dir = role_dir / "store"
                    if store_dir.exists():
                        for entry in store_dir.rglob("*"):
                            if entry.is_file():
                                global_total += entry.stat().st_size
            usage["total"] = global_total

        return usage
