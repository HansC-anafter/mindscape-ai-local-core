"""
Copy Compile Target for text/copy writing.
"""
from typing import List

from app.models.lens_kernel import EffectiveLens, CompiledLensContext
from app.models.graph import GraphNodeType, LensNodeState
from .base import CompileTargetPlugin, CompileTarget


class CopyCompileTarget(CompileTargetPlugin):
    """Copy compilation: emphasizes tone, voice, forbidden phrases"""

    def get_target(self) -> CompileTarget:
        return CompileTarget.COPY

    def compile(self, effective_lens: EffectiveLens) -> CompiledLensContext:
        """Compile for copy writing"""
        anti_goals = []
        emphasized_values = []
        style_rules = []
        tone_hints = []

        for node in effective_lens.nodes:
            if node.state == LensNodeState.OFF:
                continue

            if node.node_type == GraphNodeType.ANTI_GOAL:
                anti_goals.append(f"絕對不要使用：{node.node_label}")

            if node.node_type in {GraphNodeType.VALUE, GraphNodeType.WORLDVIEW}:
                if node.state == LensNodeState.EMPHASIZE:
                    emphasized_values.append(node.node_label)

            if node.node_type == GraphNodeType.AESTHETIC:
                if node.state == LensNodeState.EMPHASIZE:
                    tone_hints.append(f"語氣傾向：{node.node_label}")

            if node.node_type == GraphNodeType.RHYTHM:
                if node.state == LensNodeState.EMPHASIZE:
                    style_rules.append(f"節奏偏好：{node.node_label}")

        system_prompt = self._generate_system_prompt(
            anti_goals, emphasized_values, tone_hints, style_rules
        )

        return CompiledLensContext(
            system_prompt_additions=system_prompt,
            anti_goals=anti_goals,
            emphasized_values=emphasized_values,
            style_rules=style_rules + tone_hints,
            lens_hash=effective_lens.hash
        )

    def _generate_system_prompt(
        self,
        anti_goals: List[str],
        emphasized_values: List[str],
        tone_hints: List[str],
        style_rules: List[str]
    ) -> str:
        """Generate system prompt for copy writing"""
        parts = []

        if anti_goals:
            parts.append(f"【禁忌詞彙】{'; '.join(anti_goals)}")

        if emphasized_values:
            parts.append(f"【核心價值】請在文案中體現：{', '.join(emphasized_values)}")

        if tone_hints:
            parts.append(f"【語氣指引】{'; '.join(tone_hints)}")

        if style_rules:
            parts.append(f"【風格規則】{'; '.join(style_rules)}")

        return "\n".join(parts) if parts else ""

