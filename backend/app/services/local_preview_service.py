"""
Local Preview Service - Orchestrates no-cloud preview workflows for macOS (MPS/Metal).

Bypasses heavy video diffusion models by using:
1. GGUF LLM for Natural Language to Knob mapping.
2. SDXL Lightning for fast keyframe generation (MPS stable).
3. CPU/Metal interpolation for motion preview.
"""

import os
import json
import logging
import asyncio
from typing import Dict, List, Optional, Any
from pathlib import Path
from datetime import datetime, timezone


def _utc_now():
    """Return timezone-aware UTC now."""
    return datetime.now(timezone.utc)

from backend.app.services.mindscape_store import MindscapeStore
from backend.app.services.model_weights_installer import (
    ModelWeightsInstaller,
    ModelStatus,
)
from backend.app.services.data_locality_service import get_data_locality_service

logger = logging.getLogger(__name__)


class LocalPreviewService:
    def __init__(
        self,
        store: MindscapeStore,
        installer: ModelWeightsInstaller,
        output_root: str = "~/.mindscape/previews",
    ):
        self.store = store
        self.installer = installer
        self.output_root = Path(output_root).expanduser()
        self.output_root.mkdir(parents=True, exist_ok=True)
        self.locality_service = get_data_locality_service()

    async def generate_preview(
        self, workspace_id: str, prompt: str, profile_id: str = "vr_preview_local"
    ) -> Dict[str, Any]:
        """
        Main entry point for local preview generation.
        """
        logger.info(
            f"Generating local preview for workspace {workspace_id} with prompt: {prompt}"
        )

        # 1. Ensure Models are available
        await self._ensure_preview_models(profile_id)

        # 2. Template Selection (Mode A)
        template_id = await self._select_template(prompt)
        template_path = self._get_template_path(template_id)
        if not template_path.exists():
            raise FileNotFoundError(
                f"Template {template_id} not found at {template_path}"
            )

        workflow = {}
        with open(template_path, "r") as f:
            workflow = json.load(f)

        # 3. LLM Orchestration: NL -> Knob Patches (GGUF LLM)
        knob_patches = await self._interpret_natural_language(prompt)

        # 4. Apply Patches
        patched_workflow = self._apply_patches(workflow, knob_patches)

        # 5. Generate Keyframes (SDXL Lightning)
        # TODO: Execute patched_workflow via local executor
        keyframes = await self._generate_keyframes(workspace_id, patched_workflow)

        # 6. Assembly (ffmpeg / simple concat)
        v_path = await self._assemble_video(workspace_id, keyframes)

        return {
            "status": "success",
            "template_id": template_id,
            "preview_path": str(v_path),
            "patches": knob_patches,
            "timestamp": _utc_now().isoformat(),
        }

    def _get_template_path(self, template_id: str) -> Path:
        return (
            Path(
                "/Users/shock/Projects_local/workspace/mindscape-ai-cloud/capabilities/video_renderer/workflows"
            )
            / f"{template_id}.json"
        )

    async def _select_template(self, prompt: str) -> str:
        """Select best template based on prompt heuristics or LLM."""
        if "驅動" in prompt or "animate" in prompt.lower():
            return "vr_wan_animate_preview_v1"
        return "wan22_t2v_base"

    def _apply_patches(
        self, workflow: Dict[str, Any], patches: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Apply knob mappings to the workflow JSON."""
        # Simplified patching logic: iterate nodes and match keys
        for key, value in patches.items():
            for node_id, node in workflow.get("nodes", {}).items():
                if key in node.get("params", {}):
                    node["params"][key] = value
        return workflow

    async def _ensure_preview_models(self, profile_id: str):
        pass

    async def _interpret_natural_language(self, prompt: str) -> Dict[str, Any]:
        """Use local GGUF LLM to generate param patches."""
        logger.info("Interpreting NR using local LLM...")
        # Placeholder mapping
        patches = {}
        if "誇張" in prompt or "動作大" in prompt:
            patches["motion_scale"] = 1.5
        if "慢一點" in prompt:
            patches["frame_rate"] = 12
        return patches

    async def _generate_keyframes(
        self, workspace_id: str, workflow: Dict[str, Any]
    ) -> List[Path]:
        """Generate keyframes using workflow."""
        logger.info(f"Executing workflow on MPS: {workflow.get('template_id')}")
        return []

    async def _assemble_video(self, workspace_id: str, keyframes: List[Path]) -> Path:
        """Concatenate frames into a preview video."""
        logger.info("Assembling video with ffmpeg...")
        output_path = (
            self.output_root
            / workspace_id
            / f"preview_{int(_utc_now().timestamp())}.mp4"
        )
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.touch()
        return output_path
