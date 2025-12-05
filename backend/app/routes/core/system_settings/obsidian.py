"""
Obsidian configuration endpoints
"""
from fastapi import APIRouter, HTTPException
from typing import Dict, Any
import json

from .shared import settings_store
from backend.app.models.system_settings import SystemSetting, SettingType

router = APIRouter()


@router.get("/obsidian")
async def get_obsidian_config():
    """Get Obsidian configuration"""
    try:
        setting = settings_store.get_setting("obsidian_config")
        if setting:
            config = json.loads(setting.value) if isinstance(setting.value, str) else setting.value
            return config
        return {
            "vault_paths": [],
            "include_folders": ["Research", "Projects"],
            "exclude_folders": [".obsidian", "Templates"],
            "include_tags": ["research", "paper", "project"],
            "enabled": False
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get Obsidian config: {str(e)}")


@router.put("/obsidian")
async def update_obsidian_config(config: Dict[str, Any]):
    """Update Obsidian configuration"""
    try:
        setting = SystemSetting(
            key="obsidian_config",
            value=json.dumps(config),
            value_type=SettingType.JSON,
            category="tools",
            description="Obsidian vault configuration"
        )
        settings_store.save_setting(setting)
        return {"success": True, "message": "Obsidian configuration saved"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to save Obsidian config: {str(e)}")


@router.post("/obsidian/test")
async def test_obsidian_config(config: Dict[str, Any]):
    """Test Obsidian vault configuration"""
    try:
        from pathlib import Path
        vault_paths = config.get("vault_paths", [])
        valid_vaults = []

        for vault_path in vault_paths:
            vault = Path(vault_path).expanduser().resolve()
            is_valid = vault.exists() and vault.is_dir()
            valid_vaults.append({
                "path": str(vault),
                "valid": is_valid,
                "has_obsidian": (vault / ".obsidian").exists() if is_valid else False
            })

        all_valid = all(v["valid"] for v in valid_vaults)
        message = f"Found {len(valid_vaults)} vault(s), {sum(1 for v in valid_vaults if v['valid'])} valid"

        return {
            "valid": all_valid,
            "message": message,
            "vaults": valid_vaults
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to test Obsidian config: {str(e)}")

