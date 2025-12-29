"""
Preview Service for Mind-Lens.

Provides side-by-side comparison of base output vs lens output.
"""
import logging
from typing import Optional
from datetime import datetime, timezone

from app.models.lens_kernel import EffectiveLens, CompiledLensContext
from app.services.lens.effective_lens_resolver import EffectiveLensResolver
from app.services.lens.graph_to_composition_compiler import GraphToCompositionCompiler
from app.services.stores.graph_store import GraphStore
from app.services.lens.session_override_store import InMemorySessionStore
import os
import hashlib
import json

logger = logging.getLogger(__name__)


class PreviewResult:
    """Preview result with base and lens outputs"""
    def __init__(
        self,
        base_output: str,
        lens_output: str,
        diff_summary: str,
        triggered_nodes: list
    ):
        self.base_output = base_output
        self.lens_output = lens_output
        self.diff_summary = diff_summary
        self.triggered_nodes = triggered_nodes


class PreviewService:
    """Preview dual output service"""

    def __init__(self):
        if os.path.exists('/.dockerenv') or os.environ.get('PYTHONPATH') == '/app':
            db_path = '/app/data/mindscape.db'
        else:
            base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
            data_dir = os.path.join(base_dir, "data")
            os.makedirs(data_dir, exist_ok=True)
            db_path = os.path.join(data_dir, "mindscape.db")

        self.graph_store = GraphStore(db_path)
        self.session_store = InMemorySessionStore()
        self.resolver = EffectiveLensResolver(self.graph_store, self.session_store)
        self.compiler = GraphToCompositionCompiler()
        self._base_cache: dict = {}

    def _compute_base_cache_key(self, input_text: str, preview_type: str) -> str:
        """Compute cache key for base output"""
        content = json.dumps({"input": input_text, "type": preview_type}, sort_keys=True)
        return hashlib.sha256(content.encode()).hexdigest()[:16]

    async def generate_preview(
        self,
        input_text: str,
        preview_type: str,
        effective_lens: EffectiveLens,
        profile_id: str,
        workspace_id: Optional[str] = None
    ) -> PreviewResult:
        """
        Generate preview with dual output

        Strategy:
        1. Base output (without lens) → cacheable
        2. Lens output (with lens) → rerun every time
        """
        cache_key = self._compute_base_cache_key(input_text, preview_type)
        base_output = self._base_cache.get(cache_key)

        if not base_output:
            base_output = await self._execute_without_lens(input_text, preview_type, profile_id, workspace_id)
            self._base_cache[cache_key] = base_output

        lens_output = await self._execute_with_lens(
            input_text, preview_type, effective_lens, profile_id, workspace_id
        )

        diff_summary = await self._generate_diff_summary(base_output, lens_output)

        triggered_nodes = self._extract_triggered_nodes(effective_lens)

        return PreviewResult(
            base_output=base_output,
            lens_output=lens_output,
            diff_summary=diff_summary,
            triggered_nodes=triggered_nodes
        )

    async def _execute_without_lens(
        self,
        input_text: str,
        preview_type: str,
        profile_id: str,
        workspace_id: Optional[str] = None
    ) -> str:
        """Execute without lens (pure prompt)"""
        logger.info(f"Executing preview without lens: type={preview_type}")
        return f"[Base output for: {input_text[:50]}...]"

    async def _execute_with_lens(
        self,
        input_text: str,
        preview_type: str,
        effective_lens: EffectiveLens,
        profile_id: str,
        workspace_id: Optional[str] = None
    ) -> str:
        """Execute with lens"""
        logger.info(f"Executing preview with lens: type={preview_type}, hash={effective_lens.hash}")
        compiled_context = self.compiler.compile_to_prompt_context(effective_lens)
        return f"[Lens output for: {input_text[:50]}...] (with {len(compiled_context.anti_goals)} anti-goals, {len(compiled_context.emphasized_values)} values)"

    async def _generate_diff_summary(self, base_output: str, lens_output: str) -> str:
        """Generate diff summary (AI-generated)"""
        if base_output == lens_output:
            return "No significant differences detected."
        return f"Lens modified output: {len(lens_output)} chars vs {len(base_output)} chars base."

    def _extract_triggered_nodes(self, effective_lens: EffectiveLens) -> list:
        """Extract triggered nodes from effective lens"""
        return [
            {
                "node_id": node.node_id,
                "node_label": node.node_label,
                "state": node.state.value,
                "effective_scope": node.effective_scope
            }
            for node in effective_lens.nodes
            if node.state.value != "off"
        ]

