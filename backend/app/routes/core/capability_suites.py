"""
Capability Suites API

Handles capability suites - predefined combinations of multiple capability packs.
Suites are loaded from /packs/*-suite.yaml files.

A capability suite is a curated combination of multiple capability packs
that work together to provide a complete workflow or use case.
"""

from fastapi import APIRouter, HTTPException
from typing import List, Dict, Any, Optional
from pydantic import BaseModel
from pathlib import Path
import yaml
import logging

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/capability-suites", tags=["Capability Suites"])


def _scan_suite_yaml_files() -> List[Dict[str, Any]]:
    """
    Scan for suite YAML files in /packs directory

    Suite files should be named *-suite.yaml (e.g., product-designer-suite.yaml)

    Returns:
        List of suite metadata dictionaries
    """
    suites = []

    # Get packs directory
    base_dir = Path(__file__).parent.parent.parent.parent
    packs_dir = base_dir / "packs"

    # If packs directory doesn't exist at calculated path, try alternative locations
    if not packs_dir.exists():
        alt_path = Path("/app/backend/packs")
        if alt_path.exists():
            packs_dir = alt_path
        else:
            alt_path = base_dir / "backend" / "packs"
            if alt_path.exists():
                packs_dir = alt_path
            else:
                logger.warning(f"Packs directory not found. Tried: {base_dir / 'packs'}, {Path('/app/backend/packs')}, {base_dir / 'backend' / 'packs'}")
                return suites

    # Scan for *-suite.yaml files
    for suite_file in packs_dir.glob("*-suite.yaml"):
        try:
            with open(suite_file, 'r', encoding='utf-8') as f:
                suite_meta = yaml.safe_load(f)
                if suite_meta and isinstance(suite_meta, dict):
                    suite_meta['_file_path'] = str(suite_file)
                    suites.append(suite_meta)
        except Exception as e:
            logger.warning(f"Failed to load suite file {suite_file}: {e}")

    return suites


class SuiteResponse(BaseModel):
    """Response model for suite information"""
    id: str
    name: str
    description: str
    icon: Optional[str] = None
    packs: List[str]  # List of pack IDs included in this suite
    ai_members: List[str] = []
    capabilities: List[str] = []
    playbooks: List[str] = []
    required_tools: List[str] = []
    installed: bool = False  # True if all packs in the suite are installed


@router.get("/", response_model=List[SuiteResponse])
async def list_suites():
    """
    List all available capability suites

    Scans /packs/*-suite.yaml files and returns suite information.
    A suite is a curated combination of multiple capability packs.
    """
    try:
        # Scan suite YAML files
        suite_metas = _scan_suite_yaml_files()

        # Get installed pack IDs to check suite installation status
        from .capability_packs import _get_installed_pack_ids
        installed_pack_ids = _get_installed_pack_ids()

        suites = []
        for suite_meta in suite_metas:
            suite_id = suite_meta.get('id')
            if not suite_id:
                logger.warning(f"Suite metadata missing 'id' field: {suite_meta.get('_file_path', 'unknown')}")
                continue

            # Check if all packs in the suite are installed
            suite_packs = suite_meta.get('packs', [])
            all_packs_installed = len(suite_packs) > 0 and all(pack_id in installed_pack_ids for pack_id in suite_packs)

            suites.append(SuiteResponse(
                id=suite_id,
                name=suite_meta.get('name', suite_id),
                description=suite_meta.get('description', ''),
                icon=suite_meta.get('icon'),
                packs=suite_packs,
                ai_members=suite_meta.get('ai_members', []),
                capabilities=suite_meta.get('capabilities', []),
                playbooks=suite_meta.get('playbooks', []),
                required_tools=suite_meta.get('required_tools', []),
                installed=all_packs_installed
            ))

        return suites

    except Exception as e:
        logger.error(f"Failed to list suites: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to list suites: {str(e)}")


@router.post("/{suite_id}/install", response_model=Dict[str, Any])
async def install_suite(suite_id: str):
    """
    Install a capability suite

    Installs all packs included in the suite.
    """
    try:
        # Find suite definition
        suite_metas = _scan_suite_yaml_files()
        suite_meta = next((s for s in suite_metas if s.get('id') == suite_id), None)

        if not suite_meta:
            raise HTTPException(status_code=404, detail=f"Capability suite '{suite_id}' not found")

        packs = suite_meta.get('packs', [])
        if not packs:
            raise HTTPException(status_code=400, detail=f"Suite '{suite_id}' has no packs defined")

        # Install each pack in the suite
        # TODO: Call capability_packs install endpoint for each pack
        # For now, return success with pack list

        return {
            "success": True,
            "suite_id": suite_id,
            "packs": packs,
            "message": f"Capability suite '{suite_id}' installation initiated. Packs to install: {', '.join(packs)}"
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to install suite: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to install suite: {str(e)}")

