"""
Visual Compile Target for visual design.
"""
from typing import List

from app.models.lens_kernel import EffectiveLens, CompiledLensContext
from app.models.graph import GraphNodeType, LensNodeState
from .base import CompileTargetPlugin, CompileTarget


class VisualCompileTarget(CompileTargetPlugin):
    """Visual compilation: emphasizes color, mood, composition"""

    def get_target(self) -> CompileTarget:
        return CompileTarget.VISUAL

    def compile(self, effective_lens: EffectiveLens) -> CompiledLensContext:
        """Compile for visual design"""
        anti_goals = []
        emphasized_values = []
        style_rules = []
        visual_hints = []

        for node in effective_lens.nodes:
            if node.state == LensNodeState.OFF:
                continue

            if node.node_type == GraphNodeType.ANTI_GOAL:
                anti_goals.append(f"視覺禁忌：{node.node_label}")

            if node.node_type == GraphNodeType.AESTHETIC:
                if node.state == LensNodeState.EMPHASIZE:
                    visual_hints.append(f"視覺風格：{node.node_label}")

            if node.node_type == GraphNodeType.WORLDVIEW:
                if node.state == LensNodeState.EMPHASIZE:
                    visual_hints.append(f"象徵意義：{node.node_label}")

            if node.node_type == GraphNodeType.VALUE:
                if node.state == LensNodeState.EMPHASIZE:
                    emphasized_values.append(node.node_label)

        system_prompt = self._generate_system_prompt(
            anti_goals, emphasized_values, visual_hints, style_rules
        )

        return CompiledLensContext(
            system_prompt_additions=system_prompt,
            anti_goals=anti_goals,
            emphasized_values=emphasized_values,
            style_rules=visual_hints + style_rules,
            lens_hash=effective_lens.hash
        )

    def _generate_system_prompt(
        self,
        anti_goals: List[str],
        emphasized_values: List[str],
        visual_hints: List[str],
        style_rules: List[str]
    ) -> str:
        """Generate system prompt for visual design"""
        parts = []

        if anti_goals:
            parts.append(f"【視覺禁忌】{'; '.join(anti_goals)}")

        if emphasized_values:
            parts.append(f"【核心價值】請在視覺中體現：{', '.join(emphasized_values)}")

        if visual_hints:
            parts.append(f"【視覺指引】{'; '.join(visual_hints)}")

        if style_rules:
            parts.append(f"【風格規則】{'; '.join(style_rules)}")

        return "\n".join(parts) if parts else ""

