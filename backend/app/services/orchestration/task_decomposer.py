"""
Task Decomposer — LLM-driven task decomposition for complex requests.

Breaks a meeting decision + high-level action items into a detailed
PhaseIR DAG suitable for DispatchOrchestrator. Runs AFTER meeting
concludes, BEFORE DispatchOrchestrator.execute().

Architecture ref:
  - 缺失層 A (Task Decomposer) in task_orchestration_architecture.md §二
  - G2 in orchestration_implementation_plan.md
  - YogoCookie E2E scenario in scenario_stress_test.md §場景C

LLM adapter contract:
  The llm_adapter must implement:
      async chat_completion(messages, model, temperature, max_tokens) -> str
  Same interface as the meeting engine's provider (see _generation.py).
"""

import json
import logging
import re
import uuid
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

from backend.app.models.task_ir import PhaseIR, PhaseStatus

logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────────────────────────────
# P3-B: DecompositionPolicy — controls decomposition behavior per scale
# ──────────────────────────────────────────────────────────────────────


class DecompositionPolicy(BaseModel):
    """Large-program decomposition strategy — replaces naive param tuning.

    Drives batching, wave budgets, and recursive depth. Use
    ``from_scale`` factory to get sensible defaults per scale tier.
    """

    max_phases_per_wave: int = Field(
        default=20,
        description="Max phases dispatched per wave (avoids DAG explosion)",
    )
    wave_budget_seconds: int = Field(
        default=300,
        description="Time budget per wave in seconds",
    )
    batch_size: int = Field(
        default=10,
        description="Batch unit size (e.g. 10 posts per batch phase)",
    )
    recursive_depth: int = Field(
        default=2,
        description="Max recursion depth for iterative decomposition",
    )
    scale_tier: str = Field(
        default="standard",
        description="Scale tier: trivial, standard, program, campaign",
    )

    @classmethod
    def from_scale(cls, scale: str) -> "DecompositionPolicy":
        """Factory: select policy defaults from scale tier."""
        if scale == "campaign":
            return cls(
                max_phases_per_wave=30,
                batch_size=20,
                recursive_depth=3,
                scale_tier=scale,
            )
        if scale == "program":
            return cls(
                max_phases_per_wave=20,
                batch_size=10,
                recursive_depth=2,
                scale_tier=scale,
            )
        if scale == "trivial":
            return cls(
                max_phases_per_wave=5,
                batch_size=5,
                recursive_depth=1,
                wave_budget_seconds=120,
                scale_tier=scale,
            )
        return cls(scale_tier=scale)  # standard defaults


# ──────────────────────────────────────────────────────────────────────
# System prompt for task decomposition
# ──────────────────────────────────────────────────────────────────────

_DECOMPOSE_SYSTEM_PROMPT = """\
You are a Task Decomposer for Mindscape AI. Your job is to break down a \
high-level meeting decision and its action items into a detailed, executable \
phase list (DAG).

## Rules

1. Each phase MUST map to exactly one available playbook or tool. Do NOT \
   invent playbook codes — only use codes from the Available Playbooks and \
   Available Tools lists below.
2. Phases that can run in parallel SHOULD have the same (or empty) depends_on.
3. Phases that need upstream output MUST declare depends_on with the IDs of \
   their upstream phases.
4. Use stable phase IDs: "phase_0", "phase_1", etc.
5. Keep the total number of phases ≤ {max_phases}.
6. If a single action item implies batch work (e.g., "generate 90 posts"), \
   create ONE phase with a clear description mentioning the batch size — \
   the batch processor playbook will handle fan-out.
7. Output ONLY a JSON array. No markdown, no commentary.

## Output Schema

```json
[
  {{
    "id": "phase_0",
    "name": "short descriptive name",
    "description": "what this phase does and what artifact it produces",
    "preferred_engine": "playbook:<code>" or "tool:<code>",
    "depends_on": [],
    "tool_name": null or "<tool_code>",
    "input_params": {{}},
    "target_workspace_id": null
  }}
]
```

## Available Playbooks

{playbooks}

## Available Tools

{tools}
"""

_EXTEND_SYSTEM_PROMPT = """\
You are a Task Decomposer performing ITERATIVE EXPANSION. A previous wave of \
phases has completed. Based on their results, determine if additional phases \
are needed.

## Rules

1. Only add phases that are NECESSARY based on the completed wave results.
2. New phases MUST depend on already-completed phases (use their IDs in depends_on).
3. Each new phase MUST map to an available playbook or tool.
4. If no expansion is needed, return an empty JSON array: []
5. Output ONLY a JSON array. No markdown, no commentary.

## Completed Phase Results

{wave_results}

## Existing Phases (already planned)

{existing_phase_ids}

## Available Playbooks

{playbooks}
"""


class TaskDecomposer:
    """Decompose high-level action items into executable phases.

    Two modes:
    - passthrough: ≤ threshold items, return as-is (no LLM call)
    - decompose: > threshold items or explicitly flagged, call LLM

    The decomposer sits between the Meeting Engine's executor output
    and the IR compiler / DispatchOrchestrator:

        Meeting → ActionIntents (≤3) → Decomposer → PhaseIR[] (N) → DAG
    """

    def __init__(
        self,
        llm_adapter=None,
        model_name: str = "",
        decompose_threshold: int = 1,  # P3-B: any >1 item triggers decomposition
        max_phases: int = 200,  # P3-B: support large campaign-scale programs
        decomposition_policy=None,  # P3-B: Optional DecompositionPolicy
    ):
        self._llm = llm_adapter
        self._model_name = model_name
        self._threshold = decompose_threshold
        self._max_phases = max_phases
        self._policy = decomposition_policy

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def decompose(
        self,
        decision: str,
        action_items: List[Dict[str, Any]],
        available_playbooks: str = "",
        available_tools: str = "",
        force: bool = False,
    ) -> List[PhaseIR]:
        """Decompose action items into detailed phases.

        Args:
            decision: Final meeting decision text.
            action_items: High-level action items from meeting.
            available_playbooks: Available playbook codes (for grounding).
            available_tools: Available tool names (for grounding).
            force: Force decomposition even below threshold.

        Returns:
            List of PhaseIR ready for TaskIR compilation.
        """
        if not force and len(action_items) <= self._threshold:
            logger.info(
                "Passthrough: %d items ≤ threshold %d",
                len(action_items),
                self._threshold,
            )
            return self._passthrough(action_items)

        if not self._llm:
            logger.warning("No LLM adapter — falling back to passthrough")
            return self._passthrough(action_items)

        return await self._llm_decompose(
            decision, action_items, available_playbooks, available_tools
        )

    async def extend(
        self,
        existing_phases: List[PhaseIR],
        wave_results: Dict[str, Any],
        decision: str,
        available_playbooks: str = "",
    ) -> Optional[List[PhaseIR]]:
        """Iterative decomposition — extend phases based on wave results.

        Called by the Runtime Supervisor (G3) when a completed wave
        reveals that additional sub-tasks are needed.

        Args:
            existing_phases: Current PhaseIR list in the TaskIR.
            wave_results: Results from the completed wave.
            decision: Original meeting decision for context.
            available_playbooks: Available playbook codes.

        Returns:
            New PhaseIR list to append, or None if no expansion needed.
        """
        if not self._llm:
            logger.debug("No LLM adapter — skipping iterative extend")
            return None

        return await self._llm_extend(
            existing_phases, wave_results, decision, available_playbooks
        )

    # ------------------------------------------------------------------
    # Passthrough (no LLM)
    # ------------------------------------------------------------------

    def _passthrough(self, action_items: List[Dict[str, Any]]) -> List[PhaseIR]:
        """Convert action items directly to PhaseIR (no decomposition)."""
        phases = []
        for idx, item in enumerate(action_items):
            engine = item.get("engine")
            if not engine:
                playbook_code = item.get("playbook_code")
                if playbook_code:
                    engine = f"playbook:{playbook_code}"
                elif item.get("tool_name"):
                    engine = f"tool:{item['tool_name']}"
                else:
                    engine = "agent:auto"

            phases.append(
                PhaseIR(
                    id=item.get("intent_id", f"phase_{idx}"),
                    name=item.get("title", f"Action {idx + 1}"),
                    description=item.get("description", ""),
                    status=PhaseStatus.PENDING,
                    preferred_engine=engine,
                    depends_on=item.get("depends_on"),
                    target_workspace_id=item.get("target_workspace_id"),
                    tool_name=item.get("tool_name"),
                    input_params=item.get("input_params"),
                )
            )
        return phases

    # ------------------------------------------------------------------
    # LLM decomposition (Phase 2b)
    # ------------------------------------------------------------------

    async def _llm_decompose(
        self,
        decision: str,
        action_items: List[Dict[str, Any]],
        available_playbooks: str,
        available_tools: str,
    ) -> List[PhaseIR]:
        """Use LLM to decompose into detailed phases."""
        import inspect

        system_prompt = _DECOMPOSE_SYSTEM_PROMPT.format(
            max_phases=self._max_phases,
            playbooks=available_playbooks or "(none provided)",
            tools=available_tools or "(none provided)",
        )

        # Build user prompt
        items_summary = json.dumps(
            [
                {
                    "title": i.get("title", ""),
                    "description": i.get("description", ""),
                    "playbook_code": i.get("playbook_code"),
                    "tool_name": i.get("tool_name"),
                }
                for i in action_items
            ],
            ensure_ascii=False,
            indent=2,
        )

        user_prompt = (
            f"## Meeting Decision\n\n{decision}\n\n"
            f"## Action Items to Decompose\n\n{items_summary}\n\n"
            f"Decompose these into a detailed phase DAG. "
            f"Output ONLY the JSON array."
        )

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]

        try:
            call_kwargs: Dict[str, Any] = {
                "messages": messages,
                "temperature": 0.2,
                "max_tokens": 4096,
            }
            if self._model_name:
                call_kwargs["model"] = self._model_name

            # Adapt to provider signature (same pattern as _generation.py)
            sig = inspect.signature(self._llm.chat_completion)
            allowed = set(sig.parameters.keys())
            kwargs = {k: v for k, v in call_kwargs.items() if k in allowed}
            if "messages" not in kwargs:
                kwargs["messages"] = messages

            raw_output = await self._llm.chat_completion(**kwargs)
            raw_output = str(raw_output).strip()

            phases_data = self._extract_json_array(raw_output)
            if not phases_data:
                logger.warning(
                    "LLM decomposition returned no phases — "
                    "falling back to passthrough"
                )
                return self._passthrough(action_items)

            phases = self._parse_phases(phases_data)
            logger.info(
                "LLM decomposed %d action items into %d phases",
                len(action_items),
                len(phases),
            )
            return phases

        except Exception as exc:
            logger.warning(
                "LLM decomposition failed — falling back to passthrough: %s",
                exc,
            )
            return self._passthrough(action_items)

    async def _llm_extend(
        self,
        existing_phases: List[PhaseIR],
        wave_results: Dict[str, Any],
        decision: str,
        available_playbooks: str,
    ) -> Optional[List[PhaseIR]]:
        """Use LLM to determine if wave results require additional phases."""
        import inspect

        # Summarize wave results for the prompt
        results_summary = json.dumps(
            {
                pid: {
                    "playbook_code": r.get("playbook_code"),
                    "execution_id": r.get("execution_id"),
                }
                for pid, r in wave_results.items()
                if isinstance(r, dict)
            },
            ensure_ascii=False,
            indent=2,
        )

        existing_ids = [p.id for p in existing_phases]

        system_prompt = _EXTEND_SYSTEM_PROMPT.format(
            wave_results=results_summary,
            existing_phase_ids=", ".join(existing_ids),
            playbooks=available_playbooks or "(none provided)",
        )

        user_prompt = (
            f"## Original Decision\n\n{decision}\n\n"
            f"Based on the completed wave results, do any additional "
            f"phases need to be added? Output ONLY the JSON array "
            f"(empty [] if none needed)."
        )

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]

        try:
            call_kwargs: Dict[str, Any] = {
                "messages": messages,
                "temperature": 0.2,
                "max_tokens": 2048,
            }
            if self._model_name:
                call_kwargs["model"] = self._model_name

            sig = inspect.signature(self._llm.chat_completion)
            allowed = set(sig.parameters.keys())
            kwargs = {k: v for k, v in call_kwargs.items() if k in allowed}
            if "messages" not in kwargs:
                kwargs["messages"] = messages

            raw_output = await self._llm.chat_completion(**kwargs)
            raw_output = str(raw_output).strip()

            phases_data = self._extract_json_array(raw_output)
            if not phases_data:
                return None

            new_phases = self._parse_phases(phases_data)
            if not new_phases:
                return None

            # Ensure new phase IDs don't collide with existing
            existing_id_set = set(existing_ids)
            for p in new_phases:
                if p.id in existing_id_set:
                    p.id = f"{p.id}_{uuid.uuid4().hex[:6]}"

            logger.info("Iterative extend produced %d new phases", len(new_phases))
            return new_phases

        except Exception as exc:
            logger.warning("LLM extend failed (non-fatal): %s", exc)
            return None

    # ------------------------------------------------------------------
    # JSON parsing helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _extract_json_array(text: str) -> Optional[List[Dict[str, Any]]]:
        """Extract a JSON array from LLM output, tolerating markdown fences."""
        # Strip markdown code fences
        cleaned = re.sub(r"```(?:json)?\s*", "", text)
        cleaned = cleaned.strip()

        # Try direct parse
        try:
            parsed = json.loads(cleaned)
            if isinstance(parsed, list):
                return parsed
        except json.JSONDecodeError:
            pass

        # Try to find [...] substring
        match = re.search(r"\[.*\]", cleaned, re.DOTALL)
        if match:
            try:
                parsed = json.loads(match.group())
                if isinstance(parsed, list):
                    return parsed
            except json.JSONDecodeError:
                pass

        logger.warning("Could not extract JSON array from LLM output")
        return None

    def _parse_phases(self, phases_data: List[Dict[str, Any]]) -> List[PhaseIR]:
        """Parse JSON phase dicts into PhaseIR objects."""
        phases = []
        for idx, item in enumerate(phases_data[: self._max_phases]):
            phase_id = item.get("id", f"phase_{idx}")

            # Resolve engine
            engine = item.get("preferred_engine")
            if not engine:
                tool_name = item.get("tool_name")
                if tool_name:
                    engine = f"tool:{tool_name}"
                else:
                    engine = "agent:auto"

            try:
                phases.append(
                    PhaseIR(
                        id=phase_id,
                        name=item.get("name", f"Phase {idx + 1}"),
                        description=item.get("description", ""),
                        status=PhaseStatus.PENDING,
                        preferred_engine=engine,
                        depends_on=item.get("depends_on") or None,
                        target_workspace_id=item.get("target_workspace_id"),
                        tool_name=item.get("tool_name"),
                        input_params=item.get("input_params"),
                    )
                )
            except Exception as exc:
                logger.warning("Skipping malformed phase at index %d: %s", idx, exc)

        return phases
