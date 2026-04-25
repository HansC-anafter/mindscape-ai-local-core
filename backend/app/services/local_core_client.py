"""Compatibility client for local-core composition and governed LLM services."""

from datetime import datetime, timezone
import logging
import uuid
from typing import Any, Dict, Optional


def _utc_now():
    """Return timezone-aware UTC now."""
    return datetime.now(timezone.utc)

try:
    from .lens.mind_lens_service import MindLensService
    from ..models.mind_lens import MindLensInstance
except ImportError:
    MindLensService = None
    MindLensInstance = None

try:
    from .lens.composition_service import CompositionService
    from .lens.fusion_service import FusionService
    from ..models.lens_composition import LensComposition
except ImportError:
    CompositionService = None
    FusionService = None
    LensComposition = None

logger = logging.getLogger(__name__)


class LocalCoreClient:
    """Client for internal service interactions."""

    def __init__(self):
        if MindLensService:
            self.mind_lens_service = MindLensService()
        else:
            self.mind_lens_service = None
            logger.warning("MindLensService not available for LocalCoreClient")
        self._composition_service = CompositionService() if CompositionService else None
        self._fusion_service = FusionService() if FusionService else None
        self._llm_manager = None

    async def create_mind_lens_instance(
        self,
        workspace_id: str,
        user_id: str,
        label: str,
        description: str,
        constraints: Dict[str, Any],
        syntax: Dict[str, Any],
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Create a new Mind Lens instance."""

        instance_id = str(uuid.uuid4())

        if not self.mind_lens_service or not MindLensInstance:
            logger.warning(
                "Mocking create_mind_lens_instance because MindLensService is unavailable"
            )
            return {"lens_instance_id": instance_id, "status": "mocked"}

        try:
            instance = MindLensInstance(
                mind_lens_id=instance_id,
                schema_id="default",
                owner_user_id=user_id,
                role=metadata.get("role", "custom") if metadata else "custom",
                label=label,
                description=description,
                values={"constraints": constraints, "syntax": syntax},
                source={"workspace_id": workspace_id, "type": "preset"},
                metadata=metadata or {},
                created_at=_utc_now(),
                updated_at=_utc_now(),
            )

            result = self.mind_lens_service.create_instance(instance)

            return {"lens_instance_id": result.mind_lens_id, "status": "created"}
        except Exception as e:
            logger.error(f"Failed to create mind lens instance in LocalCoreClient: {e}")
            return {"lens_instance_id": instance_id, "status": "fallback_error"}

    def create_composition(self, composition_data: Dict[str, Any]):
        """Create a composition using the canonical composition service."""
        if not self._composition_service or not LensComposition:
            raise RuntimeError("CompositionService not available for LocalCoreClient")

        composition = (
            composition_data
            if isinstance(composition_data, LensComposition)
            else LensComposition(**composition_data)
        )
        return self._composition_service.create_composition(composition)

    def get_composition(self, composition_id: str):
        """Get a composition using the canonical composition service."""
        if not self._composition_service:
            raise RuntimeError("CompositionService not available for LocalCoreClient")
        return self._composition_service.get_composition(composition_id)

    async def fuse_composition(self, composition_id: str) -> Dict[str, Any]:
        """Fuse a composition and normalize the response for capability consumers."""
        if not self._composition_service or not self._fusion_service or not self.mind_lens_service:
            raise RuntimeError("Fusion services not available for LocalCoreClient")

        composition = self._composition_service.get_composition(composition_id)
        if not composition:
            raise ValueError(f"Composition {composition_id} not found")

        lens_instances = {}
        for lens_ref in composition.lens_stack:
            lens_instance = self.mind_lens_service.get_instance(lens_ref.lens_instance_id)
            if lens_instance:
                lens_instances[lens_ref.lens_instance_id] = lens_instance

        fused = self._fusion_service.fuse_composition(composition, lens_instances)
        fused_values = fused.fused_values or {}

        return {
            "composition_id": composition.composition_id,
            "workspace_id": composition.workspace_id,
            "fusion_strategy": fused.fusion_strategy,
            "source_lenses": fused.source_lenses,
            "fusion_log": fused.fusion_log,
            "fused_values": fused_values,
            "fused_constraints": fused_values.get("constraints", {}),
            "fused_syntax": fused_values.get("syntax", {}),
        }

    def _get_llm_manager(self):
        """Lazily create the canonical LLM manager for compatibility clients."""
        if self._llm_manager is None:
            from backend.app.shared.llm_provider_helper import (
                create_llm_provider_manager,
            )

            self._llm_manager = create_llm_provider_manager()
        return self._llm_manager

    async def call_llm(
        self,
        *,
        prompt: str,
        context: Optional[Dict[str, Any]] = None,
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
        workspace_id: Optional[str] = None,
        purpose: str = "local_core_client.call_llm",
        stage_name: str = "plan_generation",
        risk_level: str = "read",
    ) -> Dict[str, Any]:
        """Call the canonical governed LLM route from compatibility clients."""
        from backend.app.shared.llm_utils import build_prompt, call_llm

        messages = build_prompt(user_prompt=prompt, context=context)
        return await call_llm(
            messages=messages,
            llm_provider=self._get_llm_manager(),
            workspace_id=workspace_id,
            temperature=temperature,
            max_tokens=max_tokens,
            purpose=purpose,
            stage_name=stage_name,
            risk_level=risk_level,
        )
