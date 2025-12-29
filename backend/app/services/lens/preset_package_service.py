"""
Preset Package Service for Mind-Lens unified implementation.

Handles packaging, publishing, and installation of lens presets.
"""
import uuid
import hashlib
import json
import logging
from typing import Optional
from datetime import datetime, timezone

from backend.app.services.stores.graph_store import GraphStore
from backend.app.models.lens_package import LensPresetPackage
from backend.app.models.graph import MindLensProfile, LensProfileNode
import os

logger = logging.getLogger(__name__)


class PresetPackageService:
    """Service for managing preset packages"""

    def __init__(self, graph_store: Optional[GraphStore] = None):
        if graph_store:
            self.graph_store = graph_store
        else:
            if os.path.exists('/.dockerenv') or os.environ.get('PYTHONPATH') == '/app':
                db_path = '/app/data/mindscape.db'
            else:
                base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
                data_dir = os.path.join(base_dir, "data")
                os.makedirs(data_dir, exist_ok=True)
                db_path = os.path.join(data_dir, "mindscape.db")
            self.graph_store = GraphStore(db_path)

    def package(self, preset_id: str, author: str, license: str = "MIT") -> LensPresetPackage:
        """
        Package preset into distributable format

        Args:
            preset_id: Preset ID to package
            author: Package author
            license: Package license

        Returns:
            LensPresetPackage
        """
        preset = self.graph_store.get_lens_profile(preset_id)
        if not preset:
            raise ValueError(f"Preset {preset_id} not found")

        profile_nodes = self.graph_store.get_lens_profile_nodes(preset_id)
        all_nodes = self.graph_store.list_nodes(profile_id=preset.profile_id, is_active=True, limit=10000)
        all_edges = self.graph_store.list_edges(profile_id=preset.profile_id)

        package_nodes = [node for node in all_nodes]
        package_edges = [edge for edge in all_edges]

        content_dict = {
            "nodes": [n.dict() for n in package_nodes],
            "profile_nodes": [pn.dict() for pn in profile_nodes],
            "edges": [e.dict() for e in package_edges]
        }
        content_json = json.dumps(content_dict, sort_keys=True, default=str)
        checksum = hashlib.sha256(content_json.encode()).hexdigest()

        package = LensPresetPackage(
            id=str(uuid.uuid4()),
            name=preset.name,
            description=preset.description or "",
            version="1.0.0",
            author=author,
            license=license,
            nodes=package_nodes,
            profile_nodes=profile_nodes,
            edges=package_edges,
            checksum=checksum,
            tags=[],
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc)
        )

        return package

    def publish(self, package_id: str) -> str:
        """
        Publish package to Site Hub

        Args:
            package_id: Package ID

        Returns:
            Published package URL or ID

        Note: This is a placeholder for future Site Hub integration
        """
        logger.info(f"Publishing package {package_id} to Site Hub (not implemented yet)")
        return f"site-hub://packages/{package_id}"

    def install(self, package: LensPresetPackage, target_profile_id: str) -> MindLensProfile:
        """
        Install package to local profile

        Args:
            package: LensPresetPackage to install
            target_profile_id: Target profile ID

        Returns:
            Installed MindLensProfile
        """
        from backend.app.models.graph import MindLensProfileCreate

        installed_preset = MindLensProfileCreate(
            name=f"{package.name} (imported)",
            description=package.description,
            is_default=False,
            active_node_ids=[]
        )

        created_preset = self.graph_store.create_lens_profile(installed_preset, target_profile_id)

        for profile_node in package.profile_nodes:
            self.graph_store.upsert_lens_profile_node(
                preset_id=created_preset.id,
                node_id=profile_node.node_id,
                state=profile_node.state
            )

        return self.graph_store.get_lens_profile(created_preset.id)

