"""
SemanticNormalizer — L2-Online: parse executor output → ActionIntent[].

Sits between raw executor JSON/text and the IR compiler.  Responsible for:
- Extracting structured action items from executor output
- Minting stable intent_ids (INV-1)
- Resolving tool/playbook references where possible
- Flagging low-confidence items
"""

from __future__ import annotations

import json
import logging
import re
import uuid
from typing import Any, Dict, List, Optional

from backend.app.models.action_intent import ActionIntent, IntentConfidence

logger = logging.getLogger(__name__)


class SemanticNormalizer:
    """
    Parse executor output into structured ActionIntent list.

    This is the L2-Online bridge between raw LLM executor output
    and the structured TaskIR compilation pipeline.
    """

    def normalize(
        self,
        executor_output: str,
        decision: str = "",
        *,
        workspace_id: Optional[str] = None,
    ) -> List[ActionIntent]:
        """
        Parse executor output into ActionIntent[].

        Args:
            executor_output: Raw text/JSON from executor.
            decision: Meeting decision text (fallback context).
            workspace_id: Default workspace for routing.

        Returns:
            List of ActionIntent instances.
        """
        if not executor_output or not executor_output.strip():
            # No output → single intent from decision
            if decision:
                return [
                    ActionIntent(
                        title="Execute Decision",
                        description=decision,
                        confidence=IntentConfidence.LOW,
                        target_workspace_id=workspace_id,
                    )
                ]
            return []

        # Try JSON extraction first
        items = self._try_parse_json(executor_output)
        if items:
            intents = self._build_intents_from_items(items, workspace_id)
            logger.info(
                "[SemanticNormalizer] Parsed %d intents from JSON", len(intents)
            )
            return intents

        # Fallback: bullet-point parsing
        intents = self._parse_bullets(executor_output, workspace_id)
        if intents:
            logger.info(
                "[SemanticNormalizer] Parsed %d intents from bullets", len(intents)
            )
            return intents

        # Last resort: single intent from full text
        return [
            ActionIntent(
                title=executor_output[:100].strip(),
                description=executor_output,
                confidence=IntentConfidence.LOW,
                target_workspace_id=workspace_id,
            )
        ]

    def _build_intents_from_items(
        self, items: List[Dict[str, Any]], default_ws: Optional[str] = None
    ) -> List[ActionIntent]:
        """Build intents in two passes so legacy index deps become intent IDs."""
        intents: List[ActionIntent] = []
        raw_dependencies: List[Any] = []

        for item in items:
            intents.append(self._dict_to_intent(item, default_ws, depends_on=None))
            raw_dependencies.append(self._extract_raw_dependencies(item))

        resolved_intents: List[ActionIntent] = []
        for intent, raw_deps in zip(intents, raw_dependencies):
            resolved_depends_on = self._resolve_dependencies(raw_deps, intents)
            resolved_intents.append(
                intent.model_copy(update={"depends_on": resolved_depends_on})
            )

        return resolved_intents

    def _dict_to_intent(
        self,
        d: Dict[str, Any],
        default_ws: Optional[str] = None,
        *,
        depends_on: Optional[List[str]] = None,
    ) -> ActionIntent:
        """Convert a parsed dict to ActionIntent."""
        title = d.get("title") or d.get("action") or "Untitled"
        desc = d.get("description") or d.get("detail") or ""
        assignee = d.get("assignee") or d.get("owner") or ""

        # Resolve engine hint
        engine = d.get("engine")
        if not engine:
            playbook_code = d.get("playbook_code")
            if playbook_code:
                engine = f"playbook:{playbook_code}"

        # Confidence: items with tool or playbook are HIGH, otherwise MEDIUM
        has_actuator = bool(d.get("tool_name") or d.get("playbook_code"))
        confidence = IntentConfidence.HIGH if has_actuator else IntentConfidence.MEDIUM

        # v3.1 F1: Extract capability_profile for model routing
        cap_profile = d.get("capability_profile")
        if not cap_profile and d.get("playbook_code"):
            cap_profile = self._infer_capability_profile(d["playbook_code"])

        return ActionIntent(
            title=title,
            description=desc,
            assignee=assignee,
            confidence=confidence,
            tool_name=d.get("tool_name"),
            playbook_code=d.get("playbook_code"),
            input_params=d.get("input_params"),
            target_workspace_id=d.get("target_workspace_id") or default_ws,
            depends_on=depends_on,
            priority=d.get("priority"),
            engine=engine,
            asset_refs=d.get("asset_refs") or [],
            capability_profile=cap_profile,
        )

    @staticmethod
    def _extract_raw_dependencies(d: Dict[str, Any]) -> Any:
        """Read legacy/new dependency fields before typed normalization."""
        if d.get("blocked_by") is not None:
            return d.get("blocked_by")
        return d.get("depends_on")

    def _resolve_dependencies(
        self, raw_dependencies: Any, intents: List[ActionIntent]
    ) -> Optional[List[str]]:
        """Normalize mixed legacy deps to canonical intent IDs."""
        if not isinstance(raw_dependencies, list):
            return None

        resolved: List[str] = []
        for dep in raw_dependencies:
            dep_id = self._resolve_dependency(dep, intents)
            if dep_id and dep_id not in resolved:
                resolved.append(dep_id)

        return resolved or None

    def _resolve_dependency(
        self, dependency: Any, intents: List[ActionIntent]
    ) -> Optional[str]:
        """Resolve one dependency value to an intent_id."""
        if isinstance(dependency, int):
            return self._resolve_dependency_index(dependency, intents)

        if isinstance(dependency, str):
            dep = dependency.strip()
            if not dep:
                return None
            if dep.isdigit():
                return self._resolve_dependency_index(int(dep), intents)
            return dep

        logger.warning(
            "[SemanticNormalizer] Ignoring unsupported dependency type: %r",
            dependency,
        )
        return None

    def _resolve_dependency_index(
        self, index: int, intents: List[ActionIntent]
    ) -> Optional[str]:
        """Translate legacy 0-based blocked_by index to stable intent_id."""
        if 0 <= index < len(intents):
            return intents[index].intent_id
        logger.warning(
            "[SemanticNormalizer] Ignoring out-of-range dependency index %s for %d intents",
            index,
            len(intents),
        )
        return None

    def _try_parse_json(self, text: str) -> Optional[List[Dict[str, Any]]]:
        """Try to extract JSON array or object from text."""
        # Try direct parse
        stripped = text.strip()
        for attempt in [stripped, self._extract_json_block(stripped)]:
            if not attempt:
                continue
            try:
                parsed = json.loads(attempt)
                if isinstance(parsed, list):
                    return parsed
                if isinstance(parsed, dict):
                    # Single action item as object
                    items = parsed.get("action_items") or parsed.get("actions")
                    if isinstance(items, list):
                        return items
                    return [parsed]
            except (json.JSONDecodeError, ValueError):
                continue
        return None

    @staticmethod
    def _extract_json_block(text: str) -> Optional[str]:
        """Extract JSON from markdown fenced code block or raw brackets."""
        # Try fenced code block
        match = re.search(r"```(?:json)?\s*\n(.*?)```", text, re.DOTALL)
        if match:
            return match.group(1).strip()

        # Try raw bracket extraction
        for start, end in [("[", "]"), ("{", "}")]:
            idx_start = text.find(start)
            idx_end = text.rfind(end)
            if idx_start >= 0 and idx_end > idx_start:
                return text[idx_start : idx_end + 1]
        return None

    def _parse_bullets(
        self, text: str, default_ws: Optional[str] = None
    ) -> List[ActionIntent]:
        """Parse bullet-point style action items."""
        lines = text.strip().split("\n")
        intents: List[ActionIntent] = []

        for line in lines:
            line = line.strip()
            # Match lines starting with -, *, or numbered
            match = re.match(r"^[-*•]\s+(.+)$|^(\d+)[.)]\s+(.+)$", line)
            if match:
                title = (match.group(1) or match.group(3) or "").strip()
                if title and len(title) > 3:
                    intents.append(
                        ActionIntent(
                            title=title[:200],
                            description=title,
                            confidence=IntentConfidence.LOW,
                            target_workspace_id=default_ws,
                        )
                    )

        return intents

    @staticmethod
    def _infer_capability_profile(playbook_code: str) -> Optional[str]:
        """Infer capability_profile from a playbook's execution_profile.

        v3.1 F1: If the playbook spec declares an execution_profile with
        modalities or reasoning, derive a capability_profile string.
        """
        try:
            from backend.app.services.playbook_loaders import PlaybookJsonLoader

            pb = PlaybookJsonLoader.load_playbook_json(playbook_code)
            if pb and pb.execution_profile:
                ep = pb.execution_profile
                # Vision modality takes priority
                if "vision" in (ep.get("modalities") or []):
                    return "vision"
                # Otherwise use reasoning tier
                reasoning = ep.get("reasoning")
                if reasoning and reasoning != "standard":
                    return reasoning
        except Exception:
            pass
        return None
