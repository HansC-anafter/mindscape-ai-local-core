"""Immutable host-asset preparation and publication for the existing install saga."""

from __future__ import annotations

from hashlib import sha256
import json
import os
from pathlib import Path, PurePosixPath
import shutil
import stat
from typing import Any

from backend.app.routes.core.capability_install_core.install_commit_core.filesystem_saga import (
    PreparedCapabilityTree,
)

from .runtime_assets_installer_support import (
    resolve_capability_host_runtime_root,
)


HOST_ASSET_SCHEMA = "mindscape.capability-host-assets.v1"


class RuntimeAssetsInstallerHostAssetsMixin:
    def prepare_host_assets(
        self,
        *,
        cap_dir: Path,
        manifest: dict[str, Any],
        prepared: PreparedCapabilityTree,
        result: Any,
    ) -> None:
        inventory_path = cap_dir / "host_assets.json"
        if not inventory_path.exists():
            if manifest.get("host_requirements") is not None:
                raise ValueError("capability_host_assets_inventory_missing")
            return
        inventory = _load_inventory(inventory_path)
        _validate_inventory_identity(inventory, manifest)
        host_root = resolve_capability_host_runtime_root(self.local_core_root)
        _require_safe_runtime_root(host_root)
        target_dir = (
            host_root
            / inventory["capability_code"]
            / f"{inventory['capability_version']}-{inventory['tree_sha256']}"
        )
        staging_dir = (
            host_root
            / ".staging"
            / prepared.install_id
            / inventory["capability_code"]
        )
        prepared.host_runtime_target_dir = target_dir
        prepared.host_runtime_tree_digest = inventory["tree_sha256"]
        if target_dir.exists():
            _verify_installed_tree(target_dir, inventory)
            prepared.host_runtime_reused = True
            result.add_installed(
                "host_runtime_assets",
                inventory["tree_sha256"],
            )
            return
        if staging_dir.exists() or staging_dir.is_symlink():
            raise ValueError("capability_host_runtime_staging_exists")
        staging_dir.mkdir(parents=True, mode=0o700)
        try:
            for asset in inventory["assets"]:
                relative = _safe_relative_path(asset["path"])
                source = cap_dir.joinpath(*relative.parts)
                source_stat = source.lstat()
                if (
                    stat.S_ISLNK(source_stat.st_mode)
                    or not stat.S_ISREG(source_stat.st_mode)
                ):
                    raise ValueError("capability_host_asset_source_invalid")
                payload = source.read_bytes()
                _require_asset_identity(asset, payload, source_stat.st_mode)
                destination = staging_dir.joinpath(*relative.parts)
                destination.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
                _write_exclusive(destination, payload, int(asset["mode"], 8))
            _write_exclusive(
                staging_dir / "host_assets.json",
                _canonical_bytes(inventory) + b"\n",
                0o600,
            )
            _verify_installed_tree(staging_dir, inventory)
            _fsync_tree(staging_dir)
        except Exception:
            shutil.rmtree(staging_dir, ignore_errors=True)
            _prune_empty_parents(staging_dir.parent, stop=host_root)
            raise
        prepared.host_runtime_staging_dir = staging_dir
        result.add_installed(
            "host_runtime_assets",
            inventory["tree_sha256"],
        )

    def publish_host_assets(self, prepared: PreparedCapabilityTree) -> None:
        if prepared.host_runtime_target_dir is None:
            return
        if prepared.host_runtime_reused:
            prepared.host_runtime_published = True
            return
        staging = prepared.host_runtime_staging_dir
        target = prepared.host_runtime_target_dir
        if staging is None or not staging.is_dir():
            raise RuntimeError("capability_host_runtime_not_prepared")
        target.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        if os.stat(staging).st_dev != os.stat(target.parent).st_dev:
            raise OSError("capability_host_runtime_publish_cross_device")
        staging.rename(target)
        prepared.host_runtime_published = True

    def restore_host_assets(self, prepared: PreparedCapabilityTree) -> None:
        if (
            not prepared.host_runtime_published
            or prepared.host_runtime_reused
            or prepared.host_runtime_target_dir is None
        ):
            return
        target = prepared.host_runtime_target_dir
        staging = prepared.host_runtime_staging_dir
        if staging is None:
            raise RuntimeError("capability_host_runtime_staging_identity_missing")
        staging.parent.mkdir(parents=True, exist_ok=True)
        if target.exists():
            target.rename(staging)
        prepared.host_runtime_published = False

    def finalize_host_assets(self, prepared: PreparedCapabilityTree) -> None:
        staging = prepared.host_runtime_staging_dir
        if staging is not None and staging.exists():
            shutil.rmtree(staging)
        _prune_empty_parents(
            staging.parent if staging is not None else None,
            stop=(
                resolve_capability_host_runtime_root(self.local_core_root)
                if staging is not None
                else None
            ),
        )


def _load_inventory(path: Path) -> dict[str, Any]:
    if path.is_symlink() or not path.is_file():
        raise ValueError("capability_host_assets_inventory_invalid")
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError("capability_host_assets_inventory_invalid") from exc
    if not isinstance(value, dict):
        raise ValueError("capability_host_assets_inventory_invalid")
    return value


def _validate_inventory_identity(
    inventory: dict[str, Any],
    manifest: dict[str, Any],
) -> None:
    required = {
        "schema_version",
        "capability_code",
        "capability_version",
        "requirements",
        "assets",
        "tree_sha256",
    }
    if set(inventory) != required:
        raise ValueError("capability_host_assets_inventory_keys_invalid")
    if inventory["schema_version"] != HOST_ASSET_SCHEMA:
        raise ValueError("capability_host_assets_inventory_schema_invalid")
    if (
        inventory["capability_code"] != manifest.get("code")
        or inventory["capability_version"] != manifest.get("version")
    ):
        raise ValueError("capability_host_assets_manifest_identity_mismatch")
    tree_digest = inventory.get("tree_sha256")
    if (
        not isinstance(tree_digest, str)
        or len(tree_digest) != 64
        or sha256(
            _canonical_bytes(
                {
                    key: value
                    for key, value in inventory.items()
                    if key != "tree_sha256"
                }
            )
        ).hexdigest()
        != tree_digest
    ):
        raise ValueError("capability_host_assets_tree_digest_mismatch")
    assets = inventory.get("assets")
    if not isinstance(assets, list) or not assets:
        raise ValueError("capability_host_assets_inventory_assets_invalid")
    paths = [asset.get("path") for asset in assets if isinstance(asset, dict)]
    if len(paths) != len(assets) or paths != sorted(set(paths)):
        raise ValueError("capability_host_assets_inventory_paths_invalid")
    if inventory.get("requirements") != _expected_requirements(manifest):
        raise ValueError("capability_host_assets_requirements_mismatch")


def _expected_requirements(manifest: dict[str, Any]) -> list[dict[str, Any]]:
    declaration = manifest.get("host_requirements")
    if (
        not isinstance(declaration, dict)
        or set(declaration) != {"schema_version", "requirements"}
        or declaration.get("schema_version")
        != "mindscape.pack-host-requirements.v1"
        or not isinstance(declaration.get("requirements"), list)
        or not declaration["requirements"]
    ):
        raise ValueError("capability_host_requirements_invalid")
    exact_keys = {
        "requirement_code",
        "entrypoint",
        "operations",
        "permission_classes",
        "resource_lane",
        "share_policy",
        "runtime_assets",
    }
    expected: list[dict[str, Any]] = []
    for requirement in declaration["requirements"]:
        if not isinstance(requirement, dict) or set(requirement) != exact_keys:
            raise ValueError("capability_host_requirements_invalid")
        expected.append(
            {
                "requirement_code": requirement["requirement_code"],
                "entrypoint": requirement["entrypoint"],
                "operations": list(requirement["operations"]),
                "permission_classes": list(requirement["permission_classes"]),
                "resource_lane": requirement["resource_lane"],
                "share_policy": requirement["share_policy"],
                "runtime_assets": list(requirement["runtime_assets"]),
            }
        )
    return expected


def _require_safe_runtime_root(root: Path) -> None:
    current = root
    existing: list[Path] = []
    while current != current.parent:
        if current.exists() or current.is_symlink():
            existing.append(current)
        current = current.parent
    for candidate in existing:
        candidate_stat = candidate.lstat()
        if stat.S_ISLNK(candidate_stat.st_mode):
            raise ValueError("capability_host_runtime_root_redirected")
        if candidate == root and not stat.S_ISDIR(candidate_stat.st_mode):
            raise ValueError("capability_host_runtime_root_invalid")


def _verify_installed_tree(root: Path, inventory: dict[str, Any]) -> None:
    expected = {"host_assets.json"}
    for asset in inventory["assets"]:
        relative = _safe_relative_path(asset["path"])
        expected.add(relative.as_posix())
        installed = root.joinpath(*relative.parts)
        installed_stat = installed.lstat()
        if (
            stat.S_ISLNK(installed_stat.st_mode)
            or not stat.S_ISREG(installed_stat.st_mode)
        ):
            raise ValueError("capability_host_asset_installed_type_mismatch")
        _require_asset_identity(
            asset,
            installed.read_bytes(),
            installed_stat.st_mode,
        )
    actual = {
        path.relative_to(root).as_posix()
        for path in root.rglob("*")
        if path.is_file()
    }
    if actual != expected:
        raise ValueError("capability_host_asset_installed_tree_mismatch")


def _require_asset_identity(
    asset: dict[str, Any],
    payload: bytes,
    mode: int,
) -> None:
    if set(asset) != {"path", "sha256", "size_bytes", "mode"}:
        raise ValueError("capability_host_asset_identity_keys_invalid")
    if type(asset["size_bytes"]) is not int or asset["size_bytes"] != len(payload):
        raise ValueError("capability_host_asset_size_mismatch")
    if asset["sha256"] != sha256(payload).hexdigest():
        raise ValueError("capability_host_asset_digest_mismatch")
    if (
        not isinstance(asset["mode"], str)
        or asset["mode"] not in {"0600", "0640", "0644", "0700", "0750", "0755"}
        or stat.S_IMODE(mode) != int(asset["mode"], 8)
    ):
        raise ValueError("capability_host_asset_mode_mismatch")


def _safe_relative_path(value: object) -> PurePosixPath:
    if not isinstance(value, str):
        raise ValueError("capability_host_asset_path_invalid")
    path = PurePosixPath(value)
    if (
        path.is_absolute()
        or ".." in path.parts
        or not path.parts
        or path.parts[0] not in {"scripts", "config", "services", "adapters"}
    ):
        raise ValueError("capability_host_asset_path_invalid")
    return path


def _write_exclusive(path: Path, payload: bytes, mode: int) -> None:
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, mode)
    try:
        with os.fdopen(fd, "wb", closefd=False) as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
    finally:
        os.close(fd)


def _fsync_tree(root: Path) -> None:
    for directory in sorted(
        (path for path in root.rglob("*") if path.is_dir()),
        key=lambda path: len(path.parts),
        reverse=True,
    ):
        fd = os.open(directory, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(fd)
        finally:
            os.close(fd)
    fd = os.open(root, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def _canonical_bytes(value: dict[str, Any]) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")


def _prune_empty_parents(path: Path | None, *, stop: Path | None) -> None:
    current = path
    while current is not None and stop is not None and current != stop:
        try:
            current.rmdir()
        except OSError:
            return
        current = current.parent
