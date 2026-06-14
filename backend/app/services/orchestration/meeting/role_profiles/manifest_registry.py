"""Manifest-backed registry for pack-scoped meeting role profiles."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, ClassVar, Dict, List, Optional

import yaml

from backend.app.services.orchestration.meeting.planner_contract_execution.manifest_registry import (
    PlannerContractManifestRegistry,
)


class MeetingRoleProfileManifestRegistry:
    """Read ``meeting_role_profiles`` from installed capability manifests."""

    _CACHE: ClassVar[Dict[str, tuple[int, List[Dict[str, Any]]]]] = {}

    @staticmethod
    def active_pack_id(session_metadata: Optional[Dict[str, Any]]) -> Optional[str]:
        return PlannerContractManifestRegistry.active_pack_id(session_metadata)

    def capability_manifest_paths(self, pack_id: str) -> List[Path]:
        app_dir = os.getenv("APP_DIR", "/app")
        data_dir = os.getenv("DATA_DIR", "data")
        return [
            Path(app_dir) / "backend" / "app" / "capabilities" / pack_id / "manifest.yaml",
            Path("backend/app/capabilities") / pack_id / "manifest.yaml",
            Path(data_dir) / "capabilities" / pack_id / "manifest.yaml",
        ]

    def load_profiles_for_pack(self, pack_id: str) -> List[Dict[str, Any]]:
        for manifest_path in self.capability_manifest_paths(pack_id):
            if not manifest_path.exists():
                continue
            return self._read_manifest_profiles(
                pack_id=pack_id,
                manifest_path=manifest_path,
            )
        return []

    def _read_manifest_profiles(
        self,
        *,
        pack_id: str,
        manifest_path: Path,
    ) -> List[Dict[str, Any]]:
        try:
            stat = manifest_path.stat()
        except OSError:
            return []
        cache_key = str(manifest_path)
        cached = self._CACHE.get(cache_key)
        if cached and cached[0] == stat.st_mtime_ns:
            return [dict(profile) for profile in cached[1]]

        with manifest_path.open("r", encoding="utf-8") as handle:
            manifest = yaml.safe_load(handle) or {}

        profiles: List[Dict[str, Any]] = []
        for raw_profile in manifest.get("meeting_role_profiles", []) or []:
            if not isinstance(raw_profile, dict):
                continue
            code = str(raw_profile.get("code") or "").strip()
            if not code:
                continue
            profiles.append(
                {
                    "pack_id": pack_id,
                    "code": code,
                    "display_name": str(
                        raw_profile.get("display_name") or code
                    ).strip(),
                    "match": dict(raw_profile.get("match") or {}),
                    "slot_overrides": dict(raw_profile.get("slot_overrides") or {}),
                    "planner_lane": dict(raw_profile.get("planner_lane") or {}),
                    "manifest_path": str(manifest_path),
                }
            )
        self._CACHE[cache_key] = (stat.st_mtime_ns, [dict(profile) for profile in profiles])
        return profiles
