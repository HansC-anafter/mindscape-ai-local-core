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
            "published": self.published,
            "finalized": self.finalized,
        }
