"""
Graph to Composition Compiler.

Compiles EffectiveLens into executable LensComposition or prompt context.
Implements hard/soft rule separation strategy.
Supports different compile targets via plugins.
"""
from typing import List, Optional
from app.models.lens_kernel import EffectiveLens, CompiledLensContext
from app.models.graph import GraphNodeType, LensNodeState
from app.models.lens_composition import LensComposition, LensReference, LensRole, LensModality
from app.services.lens.compile_targets import CompileTarget, CompileTargetPlugin, CopyCompileTarget, VisualCompileTarget


class GraphToCompositionCompiler:
    """Compile EffectiveLens into executable LensComposition"""

    HARD_RULES = set()  # ANTI_GOAL not in GraphNodeType enum, using empty set for now
    HARD_ISH = {GraphNodeType.VALUE, GraphNodeType.WORLDVIEW}
    SOFT = {
        GraphNodeType.AESTHETIC,
        GraphNodeType.STRATEGY,
        GraphNodeType.ROLE,
        GraphNodeType.RHYTHM,
        GraphNodeType.KNOWLEDGE
    }

    def __init__(self):
        self._target_plugins: dict = {
            CompileTarget.COPY: CopyCompileTarget(),
            CompileTarget.VISUAL: VisualCompileTarget(),
        }

    def register_target_plugin(self, plugin: CompileTargetPlugin) -> None:
        """Register a compile target plugin"""
        self._target_plugins[plugin.get_target()] = plugin

    def compile_to_prompt_context(
        self,
        effective_lens: EffectiveLens,
        target: Optional[CompileTarget] = None
    ) -> CompiledLensContext:
        """
        Compile directly into prompt-injectable context

        If target is specified, use target-specific plugin.
        Otherwise, use default hard/soft separation.
        """
        if target and target in self._target_plugins:
            plugin = self._target_plugins[target]
            return plugin.compile(effective_lens)

        return self._default_compile_to_prompt_context(effective_lens)

    def _default_compile_to_prompt_context(self, effective_lens: EffectiveLens) -> CompiledLensContext:
        """
        Default compile directly into prompt-injectable context

        Core: hard/soft separation
        """
        anti_goals = []
        emphasized_values = []
        style_rules = []

        for node in effective_lens.nodes:
            if node.state == LensNodeState.OFF:
                continue

            if node.node_type in self.HARD_RULES:
                anti_goals.append(f"絕對不要：{node.node_label}")

            if node.node_type in self.HARD_ISH and node.state == LensNodeState.EMPHASIZE:
                emphasized_values.append(node.node_label)

            if node.node_type in self.SOFT and node.state == LensNodeState.EMPHASIZE:
                style_rules.append(f"風格傾向：{node.node_label}")

        system_additions = self._generate_system_prompt(
            anti_goals, emphasized_values, style_rules
        )

        return CompiledLensContext(
            system_prompt_additions=system_additions,
            anti_goals=anti_goals,
            emphasized_values=emphasized_values,
            style_rules=style_rules,
            lens_hash=effective_lens.hash
        )

    def _generate_system_prompt(
        self,
        anti_goals: List[str],
        emphasized_values: List[str],
        style_rules: List[str]
    ) -> str:
        """Generate system prompt additions"""
        parts = []

        if anti_goals:
            parts.append(f"【禁忌規則】{'; '.join(anti_goals)}")

        if emphasized_values:
            parts.append(f"【核心價值】請在回應中體現：{', '.join(emphasized_values)}")

        if style_rules:
            parts.append(f"【風格指引】{'; '.join(style_rules)}")

        return "\n".join(parts) if parts else ""

    def compile(self, effective_lens: EffectiveLens) -> LensComposition:
        """Compile into LensComposition (for LayerStackCompiler)"""
        lens_stack = []

        hard_nodes = [
            n for n in effective_lens.nodes
            if n.node_type in self.HARD_RULES and n.state != LensNodeState.OFF
        ]
        if hard_nodes:
            lens_stack.append(LensReference(
                lens_instance_id="graph_anti_goals",
                role=LensRole.BRAND,
                modality=LensModality.TEXT,
                weight=1.0,
                priority=10,
                scope=["all"],
                locked=True,
                metadata={"labels": [n.node_label for n in hard_nodes]}
            ))

        hardish_nodes = [
            n for n in effective_lens.nodes
            if n.node_type in self.HARD_ISH and n.state == LensNodeState.EMPHASIZE
        ]
        if hardish_nodes:
            lens_stack.append(LensReference(
                lens_instance_id="graph_values",
                role=LensRole.BRAND,
                modality=LensModality.TEXT,
                weight=1.0,
                priority=5,
                scope=["all"],
                metadata={"labels": [n.node_label for n in hardish_nodes]}
            ))

        soft_nodes = [
            n for n in effective_lens.nodes
            if n.node_type in self.SOFT and n.state != LensNodeState.OFF
        ]
        if soft_nodes:
            avg_weight = sum(n.weight for n in soft_nodes) / len(soft_nodes) if soft_nodes else 1.0
            lens_stack.append(LensReference(
                lens_instance_id="graph_style",
                role=LensRole.WRITER,
                modality=LensModality.TEXT,
                weight=avg_weight,
                priority=1,
                scope=["all"],
                metadata={
                    "labels": [n.node_label for n in soft_nodes if n.state == LensNodeState.EMPHASIZE]
                }
            ))

        return LensComposition(
            composition_id=f"graph_compiled_{effective_lens.hash}",
            workspace_id=effective_lens.workspace_id or "global",
            name=f"Compiled from {effective_lens.global_preset_name}",
            lens_stack=lens_stack,
            fusion_strategy="priority_then_weighted",
            metadata={
                "source": "graph",
                "effective_lens_hash": effective_lens.hash
            }
        )

