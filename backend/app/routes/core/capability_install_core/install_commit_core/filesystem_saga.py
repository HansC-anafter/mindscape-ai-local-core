"""Typed filesystem state for retained candidate capability publication."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass
class PreparedCapabilityTree:
    """Paths owned by one install-id-scoped filesystem saga."""

    install_id: str
    capability_code: str
    staging_root: Path
    staging_cap_dir: Path
    target_cap_dir: Path
    previous_root: Path
    previous_cap_dir: Path
    host_runtime_staging_dir: Path | None = None
    host_runtime_target_dir: Path | None = None
    host_runtime_tree_digest: str | None = None
    host_runtime_reused: bool = False
    host_runtime_published: bool = False
    published: bool = False
    finalized: bool = False

    def to_receipt(self) -> dict[str, object]:
        return {
            "install_id": self.install_id,
            "capability_code": self.capability_code,
            "staging_root": str(self.staging_root),
            "staging_cap_dir": str(self.staging_cap_dir),
            "target_cap_dir": str(self.target_cap_dir),
            "previous_cap_dir": str(self.previous_cap_dir),
            "host_runtime_target_dir": (
                str(self.host_runtime_target_dir)
                if self.host_runtime_target_dir
                else None
            ),
            "host_runtime_tree_digest": self.host_runtime_tree_digest,
            "host_runtime_reused": self.host_runtime_reused,
            "host_runtime_published": self.host_runtime_published,
            "published": self.published,
            "finalized": self.finalized,
        }
