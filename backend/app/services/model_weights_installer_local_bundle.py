"""Local bundle and cache view publishing seam for model weights installer."""

import os
import shutil
from pathlib import Path
from typing import Optional

from .model_weights_installer_types import (
    DownloadError,
    ModelInfo,
    ModelStatus,
    _utc_now,
)


class ModelWeightsInstallerLocalBundleMixin:
    def _publish_model_view(
        self, model_info: ModelInfo, store_dir: Path, view_dir: Path
    ) -> None:
        """Expose the store directory through the pack-scoped view path."""
        if view_dir.exists() or view_dir.is_symlink():
            if view_dir.is_symlink() or view_dir.is_file():
                view_dir.unlink()
            else:
                shutil.rmtree(view_dir)

        relative_target = os.path.relpath(store_dir, start=view_dir.parent)
        os.symlink(relative_target, view_dir)
        model_info.local_path = view_dir
        model_info.status = ModelStatus.DOWNLOADED
        model_info.downloaded_at = _utc_now()

    def _materialize_local_bundle(
        self, model_info: ModelInfo, store_dir: Path, view_dir: Path
    ) -> None:
        """Materialize a model from pack-local bundle files without network download."""
        bundle_source = self._resolve_local_bundle_source(model_info)
        if bundle_source is None:
            raise DownloadError(
                f"Local bundle source not found for {model_info.pack_code}:{model_info.model_id}"
            )

        if store_dir.exists() or store_dir.is_symlink():
            if store_dir.is_symlink() or store_dir.is_file():
                store_dir.unlink()
            else:
                shutil.rmtree(store_dir)
        store_dir.mkdir(parents=True, exist_ok=True)

        if bundle_source.is_file():
            if len(model_info.files) != 1:
                raise DownloadError(
                    "local_bundle file source requires exactly one declared model file"
                )
            file_info = model_info.files[0]
            target_path = store_dir / file_info.filename
            target_path.parent.mkdir(parents=True, exist_ok=True)
            self._link_or_copy_local_bundle_file(bundle_source, target_path)
            file_info.local_path = target_path
            file_info.is_downloaded = True
        elif bundle_source.is_dir():
            for file_info in model_info.files:
                source_file = bundle_source / file_info.filename
                if not source_file.exists() or not source_file.is_file():
                    raise DownloadError(
                        f"Local bundle missing file {file_info.filename} for "
                        f"{model_info.pack_code}:{model_info.model_id}"
                    )
                target_path = store_dir / file_info.filename
                target_path.parent.mkdir(parents=True, exist_ok=True)
                self._link_or_copy_local_bundle_file(source_file, target_path)
                file_info.local_path = target_path
                file_info.is_downloaded = True
        else:
            raise DownloadError(
                f"Local bundle source is neither file nor directory: {bundle_source}"
            )

        self._publish_model_view(model_info, store_dir, view_dir)

    def _resolve_local_bundle_source(self, model_info: ModelInfo) -> Optional[Path]:
        """Resolve the source path for a local bundle-backed model."""
        local_bundle = model_info.local_bundle or {}
        bundle_id = str(local_bundle.get("bundle_id") or "").strip()
        relative_path_raw = str(local_bundle.get("relative_path") or "").strip()
        if not bundle_id or not relative_path_raw:
            return None

        bundle_id_path = Path(bundle_id)
        if (
            bundle_id_path.is_absolute()
            or bundle_id_path.name != bundle_id
            or any(part in {"..", "."} for part in bundle_id_path.parts)
        ):
            raise DownloadError(f"Invalid local bundle id: {bundle_id}")

        relative_path = Path(relative_path_raw)
        if relative_path.is_absolute() or any(
            part in {"..", "."} for part in relative_path.parts
        ):
            raise DownloadError(
                f"Invalid local bundle relative path: {relative_path_raw}"
            )

        app_root = Path(__file__).resolve().parent.parent
        candidate_roots = []
        if model_info.manifest_dir is not None:
            candidate_roots.append(model_info.manifest_dir)
        candidate_roots.extend(
            [
                Path(f"capabilities/{model_info.pack_code}"),
                app_root / "capabilities" / model_info.pack_code,
                app_root.parent.parent / "capabilities" / model_info.pack_code,
                Path(f"~/.mindscape/capabilities/{model_info.pack_code}").expanduser(),
            ]
        )

        seen_roots = set()
        for root in candidate_roots:
            root_key = str(root.expanduser())
            if root_key in seen_roots:
                continue
            seen_roots.add(root_key)
            candidate = root / "bundles" / bundle_id / relative_path
            if candidate.exists():
                return candidate

        return None

    def _link_or_copy_local_bundle_file(
        self, source_path: Path, target_path: Path
    ) -> None:
        """Populate the cache store from a local bundle file."""
        if target_path.exists() or target_path.is_symlink():
            if target_path.is_symlink() or target_path.is_file():
                target_path.unlink()
            else:
                shutil.rmtree(target_path)

        shutil.copy2(source_path, target_path)
