"""Installed capability manifest registry for planner contracts."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, ClassVar, Dict, Iterable, List, Optional

import yaml


class PlannerContractManifestRegistry:
    """Read planner_contract tools from installed local-core capability manifests."""

    _CACHE: ClassVar[Dict[str, tuple[int, List[Dict[str, Any]]]]] = {}

    @staticmethod
    def active_pack_id(session_metadata: Optional[Dict[str, Any]]) -> Optional[str]:
        metadata = session_metadata if isinstance(session_metadata, dict) else {}
        candidates: List[Any] = [
            metadata.get("active_capability_code"),
            metadata.get("active_pack_code"),
            metadata.get("capability_code"),
        ]
        request_contract = metadata.get("request_contract")
        if isinstance(request_contract, dict):
            aol = request_contract.get("addressable_object_layer")
            if isinstance(aol, dict):
                candidates.extend(
                    [
                        aol.get("active_capability_code"),
                        aol.get("active_pack_code"),
                        aol.get("owner_pack"),
                    ]
                )
        for candidate in candidates:
            value = str(candidate or "").strip()
            if value:
                return value
        return None

    @staticmethod
    def pack_id_from_tool_name(tool_name: Optional[str]) -> Optional[str]:
        value = str(tool_name or "").strip()
        if "." not in value:
            return None
        pack_id, _sep, _tool_code = value.partition(".")
        return pack_id or None

    def capability_manifest_paths(self, pack_id: str) -> List[Path]:
        app_dir = os.getenv("APP_DIR", "/app")
        data_dir = os.getenv("DATA_DIR", "data")
        return [
            Path(app_dir) / "backend" / "app" / "capabilities" / pack_id / "manifest.yaml",
            Path("backend/app/capabilities") / pack_id / "manifest.yaml",
            Path(data_dir) / "capabilities" / pack_id / "manifest.yaml",
        ]

    def load_planner_tools_for_pack(self, pack_id: str) -> List[Dict[str, Any]]:
        for manifest_path in self.capability_manifest_paths(pack_id):
            if not manifest_path.exists():
                continue
            return self._read_manifest_tools(pack_id=pack_id, manifest_path=manifest_path)
        return []

    def load_planner_tools(
        self,
        *,
        session_metadata: Optional[Dict[str, Any]] = None,
        tool_names: Optional[Iterable[Optional[str]]] = None,
    ) -> List[Dict[str, Any]]:
        pack_ids: List[str] = []
        active_pack = self.active_pack_id(session_metadata)
        if active_pack:
            pack_ids.append(active_pack)
        for tool_name in tool_names or []:
            pack_id = self.pack_id_from_tool_name(tool_name)
            if pack_id and pack_id not in pack_ids:
                pack_ids.append(pack_id)

        tools: List[Dict[str, Any]] = []
        seen: set[str] = set()
        for pack_id in pack_ids:
            for tool in self.load_planner_tools_for_pack(pack_id):
                canonical = str(tool.get("canonical_tool_name") or "")
                if not canonical or canonical in seen:
                    continue
                seen.add(canonical)
                tools.append(tool)
        return tools

    def _read_manifest_tools(
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
            return [dict(tool) for tool in cached[1]]

        with manifest_path.open("r", encoding="utf-8") as handle:
            manifest = yaml.safe_load(handle) or {}

        planner_tools: List[Dict[str, Any]] = []
        for tool in manifest.get("tools", []) or []:
            if not isinstance(tool, dict):
                continue
            planner_contract = tool.get("planner_contract")
            if not (
                isinstance(planner_contract, dict)
                and planner_contract.get("exposed") is True
            ):
                continue
            code = str(tool.get("code") or tool.get("name") or "").strip()
            if not code:
                continue
            canonical = code if "." in code else f"{pack_id}.{code}"
            planner_tools.append(
                {
                    "pack_id": pack_id,
                    "tool_code": code,
                    "canonical_tool_name": canonical,
                    "display_name": tool.get("display_name")
                    or tool.get("description")
                    or tool.get("name")
                    or code,
                    "planner_contract": dict(planner_contract),
                    "execution_hints": dict(
                        planner_contract.get("execution_hints")
                        if isinstance(planner_contract.get("execution_hints"), dict)
                        else {}
                    ),
                    "manifest_path": str(manifest_path),
                }
            )
        self._CACHE[cache_key] = (stat.st_mtime_ns, [dict(tool) for tool in planner_tools])
        return planner_tools
