import json
import logging
import os
import shutil
from pathlib import Path
from typing import Dict

from .install_result import InstallResult
from .runtime_assets_installer_support import _safe_asset_segment, _sha256_integrity

logger = logging.getLogger("app.services.runtime_assets_installer")


class RuntimeAssetsInstallerModelUiAssetsMixin:
    def install_database_models(
        self, cap_dir: Path, capability_code: str, result: InstallResult
    ):
        """Install capability database models"""
        database_models_dir = cap_dir / "database" / "models"
        if not database_models_dir.exists():
            return

        target_models_dir = self.local_core_root / "backend" / "app" / "models"
        target_models_dir.mkdir(parents=True, exist_ok=True)

        for model_file in database_models_dir.glob("*.py"):
            if model_file.name.startswith("__"):
                continue

            target_model_dir = target_models_dir / capability_code
            target_model_dir.mkdir(parents=True, exist_ok=True)
            target_model = target_model_dir / model_file.name

            content = None
            for encoding in ["utf-8", "utf-8-sig", "latin-1", "cp1252"]:
                try:
                    with open(model_file, "r", encoding=encoding) as f:
                        content = f.read()
                    break
                except UnicodeDecodeError:
                    continue

            if content is None:
                with open(model_file, "rb") as f:
                    raw_content = f.read()
                content = raw_content.decode("utf-8", errors="replace")

            if "from .. import Base" in content:
                content = content.replace(
                    "from .. import Base", "from database import Base"
                )

            with open(target_model, "w", encoding="utf-8") as f:
                f.write(content)

            model_name = model_file.stem
            result.add_installed("database_models", model_name)
            logger.debug(f"Installed database model: {model_file.name} (imports fixed)")

        init_file = database_models_dir / "__init__.py"
        if init_file.exists():
            target_init_dir = target_models_dir / capability_code
            target_init_dir.mkdir(parents=True, exist_ok=True)
            target_init = target_init_dir / "__init__.py"
            shutil.copy2(init_file, target_init)
            logger.debug(f"Installed database models __init__.py")

    def install_capability_models(
        self, cap_dir: Path, capability_code: str, result: InstallResult
    ):
        """Install capability models from models/ directory to app/capabilities/{capability_code}/models/"""
        models_dir = cap_dir / "models"
        if not models_dir.exists():
            return

        target_models_dir = self.capabilities_dir / capability_code / "models"
        target_models_dir.mkdir(parents=True, exist_ok=True)

        for model_file in models_dir.rglob("*"):
            if not model_file.is_file():
                continue
            if "__pycache__" in model_file.parts:
                continue

            relative_path = model_file.relative_to(models_dir)
            target_model = target_models_dir / relative_path
            target_model.parent.mkdir(parents=True, exist_ok=True)

            shutil.copy2(model_file, target_model)
            if not model_file.name.startswith("__"):
                result.add_installed("capability_models", str(relative_path))
            logger.debug(f"Installed capability model asset: {relative_path}")

    def install_ui_components(
        self, cap_dir: Path, capability_code: str, manifest: Dict, result: InstallResult
    ):
        """
        Install compiled UI assets without mutating the frontend source tree.

        Args:
            cap_dir: Extracted capability directory (from .mindpack)
            capability_code: Capability code
            manifest: Parsed manifest dict
            result: InstallResult to update
        """
        ui_components = manifest.get("ui_components", [])
        if not ui_components:
            return

        source_ui_dist_dir = cap_dir / "ui_dist"
        if not source_ui_dist_dir.exists():
            if (cap_dir / "ui").exists():
                result.add_warning(
                    f"UI source for {capability_code} was not installed; pack must include compiled ui_dist assets."
                )
            return

        dist_manifest_path = source_ui_dist_dir / "ui_dist_manifest.json"
        if not dist_manifest_path.exists():
            result.add_warning(
                f"Compiled UI assets for {capability_code} missing ui_dist_manifest.json"
            )
            return

        try:
            dist_manifest = json.loads(dist_manifest_path.read_text(encoding="utf-8"))
        except Exception as exc:
            result.add_warning(f"Failed to parse ui_dist_manifest.json: {exc}")
            return

        version_segment = _safe_asset_segment(manifest.get("version"), "unversioned")
        assets_root = Path(
            os.getenv(
                "MINDSCAPE_CAPABILITY_UI_ASSETS_DIR",
                str(self.local_core_root / "data" / "capability-ui"),
            )
        )
        target_assets_dir = assets_root / capability_code / version_segment
        if target_assets_dir.exists():
            shutil.rmtree(target_assets_dir)
        target_assets_dir.mkdir(parents=True, exist_ok=True)

        runtime_components = []
        for component in dist_manifest.get("components", []):
            component_code = component.get("code")
            asset_path = str(component.get("asset_path") or "").strip()
            if not component_code or not asset_path:
                continue
            source_asset = (source_ui_dist_dir / asset_path).resolve()
            try:
                source_asset.relative_to(source_ui_dist_dir.resolve())
            except ValueError:
                result.add_warning(f"Skipping unsafe UI asset path: {asset_path}")
                continue
            if not source_asset.exists() or not source_asset.is_file():
                result.add_warning(f"Compiled UI asset not found: {asset_path}")
                continue

            target_asset = target_assets_dir / asset_path
            target_asset.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source_asset, target_asset)
            integrity = component.get("integrity") or _sha256_integrity(target_asset)
            runtime_components.append(
                {
                    "code": component_code,
                    "asset_path": f"{version_segment}/{asset_path}",
                    "asset_url": (
                        f"/api/v1/capability-packs/installed-capabilities/"
                        f"{capability_code}/ui-assets/{version_segment}/{asset_path}"
                    ),
                    "integrity": integrity,
                    "bytes": target_asset.stat().st_size,
                    "export": component.get("export", "default"),
                    "runtime": component.get("runtime", "mindscape-react-bridge-v1"),
                }
            )
            result.add_installed("ui_components", str(component_code))

        if not runtime_components:
            return

        target_cap_dir = self.capabilities_dir / capability_code
        target_cap_dir.mkdir(parents=True, exist_ok=True)
        sidecar_path = target_cap_dir / "ui_runtime_assets.json"
        sidecar_path.write_text(
            json.dumps(
                {
                    "capability_code": capability_code,
                    "version": version_segment,
                    "components": runtime_components,
                },
                indent=2,
                sort_keys=True,
            ),
            encoding="utf-8",
        )
        logger.info(
            "Installed compiled UI runtime assets for %s: %s components",
            capability_code,
            len(runtime_components),
        )
