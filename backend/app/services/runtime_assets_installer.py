"""
Runtime Assets Installer

Install runtime assets and execute capability-specific migrations.
"""

from pathlib import Path

from .runtime_assets_installer_metadata_assets import (
    RuntimeAssetsInstallerMetadataAssetsMixin,
)
from .runtime_assets_installer_host_assets import (
    RuntimeAssetsInstallerHostAssetsMixin,
)
from .runtime_assets_installer_model_ui_assets import (
    RuntimeAssetsInstallerModelUiAssetsMixin,
)
from .runtime_assets_installer_staging import RuntimeAssetsInstallerStagingMixin
from .runtime_assets_installer_support import (
    RUNTIME_MIRROR_DIRS,
    RUNTIME_NAMESPACE_DIRS,
    SCRIPT_DIR_EXCLUDES,
    SCRIPT_FILE_EXCLUDES,
    SCRIPT_SUFFIX_EXCLUDES,
    _build_staging_root,
    _clear_directory_contents,
    _iter_runtime_mirror_files,
    _safe_asset_segment,
    _sha256_integrity,
    _should_skip_runtime_mirror_asset,
    resolve_capability_host_runtime_root,
)
from .runtime_assets_installer_tree_assets import RuntimeAssetsInstallerTreeAssetsMixin

__all__ = [
    "RUNTIME_MIRROR_DIRS",
    "RUNTIME_NAMESPACE_DIRS",
    "RuntimeAssetsInstaller",
    "SCRIPT_DIR_EXCLUDES",
    "SCRIPT_FILE_EXCLUDES",
    "SCRIPT_SUFFIX_EXCLUDES",
    "_build_staging_root",
    "_clear_directory_contents",
    "_iter_runtime_mirror_files",
    "_safe_asset_segment",
    "_sha256_integrity",
    "_should_skip_runtime_mirror_asset",
    "resolve_capability_host_runtime_root",
]


class RuntimeAssetsInstaller(
    RuntimeAssetsInstallerStagingMixin,
    RuntimeAssetsInstallerHostAssetsMixin,
    RuntimeAssetsInstallerTreeAssetsMixin,
    RuntimeAssetsInstallerModelUiAssetsMixin,
    RuntimeAssetsInstallerMetadataAssetsMixin,
):
    """Install runtime assets (tools, services, API, schema, models, migrations, UI, manifest, root files, bundles)"""

    def __init__(self, local_core_root: Path, capabilities_dir: Path):
        """
        Initialize installer

        Args:
            local_core_root: Local-core project root directory
            capabilities_dir: Directory for capability manifests
        """
        self.local_core_root = local_core_root
        self.capabilities_dir = capabilities_dir
