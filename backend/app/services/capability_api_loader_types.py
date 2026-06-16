"""Shared types and constants for capability API loading."""

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict

_APP_STATE_KEY = "capability_api_loader_state"
_VALID_ACTIVATION_POLICIES = {"startup_eager", "seed_only"}
_DEFAULT_SEED_ONLY_STARTUP_ACTIVATION_ALLOWLIST = ("character_training",)


@dataclass(frozen=True)
class CapabilityAPIDescriptor:
    """Manifest-derived descriptor for a capability API module."""

    capability_code: str
    capability_dir: Path
    manifest_path: Path
    cap_def: Dict[str, Any]


__all__ = [
    "CapabilityAPIDescriptor",
    "_APP_STATE_KEY",
    "_VALID_ACTIVATION_POLICIES",
    "_DEFAULT_SEED_ONLY_STARTUP_ACTIVATION_ALLOWLIST",
]
