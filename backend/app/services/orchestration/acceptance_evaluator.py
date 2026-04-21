"""
AcceptanceEvaluator — Deterministic quality checks for playbook outputs.

This evaluator only performs deterministic checks and does not invoke
LLM-based judges.

Checks performed:
1. Output completeness — result_data is non-empty and has expected keys
2. Output hash present — parsed_output has a non-None output_hash
3. Produces match — all declared outputs resolved
4. Acceptance tests — keyword/pattern match against result_data
5. Auto-pass — no acceptance_tests defined → pass with score=1.0
"""

import logging
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

_PREVIEW_SUCCESS_STATUSES = {"completed", "preview_done", "succeeded", "success", "done"}


@dataclass
class EvalResult:
    """Result of acceptance evaluation."""

    passed: bool
    quality_score: float  # 0.0 – 1.0
    reasons: List[str] = field(default_factory=list)
    checks: List[Dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "passed": self.passed,
            "quality_score": self.quality_score,
            "reasons": self.reasons,
            "checks": self.checks,
        }


class AcceptanceEvaluator:
    """Deterministic quality gate for playbook completion results.

    Designed to be called synchronously from ``GovernanceEngine``.
    All checks are fast, deterministic, and non-blocking.
    """

    # Keys that indicate meaningful output content
    _OUTPUT_KEYS = {"output", "steps", "result_json", "result", "data", "content"}

    def evaluate(
        self,
        *,
        result_data: Optional[Dict[str, Any]],
        parsed_output: Optional[Dict[str, Any]],
        acceptance_tests: Optional[List[str]],
        playbook_code: Optional[str] = None,
    ) -> EvalResult:
        """Run all deterministic checks and return an EvalResult.

        Parameters:
            result_data: Raw task result payload from the execution.
            parsed_output: Sidecar dict from PackDispatchAdapter.parse_result.
            acceptance_tests: List of acceptance criteria strings from
                GovernanceContext.
            playbook_code: Playbook identifier for logging.

        Returns:
            EvalResult with aggregated pass/fail, score, and per-check detail.
        """
        checks: List[Dict[str, Any]] = []

        # --- Check 1: Output completeness ---
        checks.append(self._check_output_completeness(result_data))

        # --- Check 2: Output hash present ---
        checks.append(self._check_output_hash(parsed_output))

        # --- Check 3: Produces match ---
        checks.append(self._check_produces_match(parsed_output))

        # --- Check 3b: Structured acceptance evidence ---
        evidence_check = self._check_acceptance_evidence(parsed_output)
        if evidence_check is not None:
            checks.append(evidence_check)

        # --- Check 4: Acceptance tests ---
        if acceptance_tests:
            for test_str in acceptance_tests:
                checks.append(
                    self._check_acceptance_test(test_str, result_data)
                )

        # --- Aggregate ---
        total = len(checks)
        passed_count = sum(1 for c in checks if c["passed"])
        quality_score = passed_count / total if total > 0 else 1.0
        all_passed = passed_count == total

        reasons = [c["detail"] for c in checks if not c["passed"]]

        result = EvalResult(
            passed=all_passed,
            quality_score=round(quality_score, 3),
            reasons=reasons,
            checks=checks,
        )

        logger.info(
            "AcceptanceEvaluator: pb=%s passed=%s score=%.2f checks=%d/%d",
            playbook_code or "(unknown)",
            all_passed,
            quality_score,
            passed_count,
            total,
        )

        return result

    # ------------------------------------------------------------------
    # Individual checks
    # ------------------------------------------------------------------

    def _check_output_completeness(
        self, result_data: Optional[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """Check that result_data is non-empty and has meaningful keys."""
        if not result_data or not isinstance(result_data, dict):
            return {
                "test": "output_completeness",
                "passed": False,
                "detail": "result_data is empty or not a dict",
            }

        has_content_key = bool(self._OUTPUT_KEYS & set(result_data.keys()))
        if has_content_key:
            return {
                "test": "output_completeness",
                "passed": True,
                "detail": "result_data has content keys",
            }

        # Even without standard keys, non-empty dict is partial pass
        return {
            "test": "output_completeness",
            "passed": True,
            "detail": f"result_data has {len(result_data)} keys (non-standard)",
        }

    def _check_output_hash(
        self, parsed_output: Optional[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """Check that parsed_output contains a non-None output_hash."""
        if not parsed_output or not isinstance(parsed_output, dict):
            return {
                "test": "output_hash_present",
                "passed": False,
                "detail": "parsed_output unavailable",
            }

        output_hash = parsed_output.get("output_hash")
        if output_hash:
            return {
                "test": "output_hash_present",
                "passed": True,
                "detail": f"hash={output_hash[:12]}...",
            }

        return {
            "test": "output_hash_present",
            "passed": False,
            "detail": "output_hash is None or empty",
        }

    def _check_produces_match(
        self, parsed_output: Optional[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """Check that all declared outputs resolved successfully."""
        if not parsed_output or not isinstance(parsed_output, dict):
            return {
                "test": "produces_match",
                "passed": True,
                "detail": "no produces spec to check (auto-pass)",
            }

        outputs_matched = parsed_output.get("outputs_matched")
        if not outputs_matched or not isinstance(outputs_matched, dict):
            return {
                "test": "produces_match",
                "passed": True,
                "detail": "no outputs_matched in sidecar (auto-pass)",
            }

        total = len(outputs_matched)
        resolved = sum(
            1 for v in outputs_matched.values()
            if isinstance(v, dict) and v.get("resolved")
        )
        all_resolved = resolved == total

        return {
            "test": "produces_match",
            "passed": all_resolved,
            "detail": f"{resolved}/{total} outputs resolved",
        }

    def _check_acceptance_test(
        self,
        test_str: str,
        result_data: Optional[Dict[str, Any]],
    ) -> Dict[str, Any]:
        """Match a single acceptance test against result_data.

        Strategy: case-insensitive keyword search through the
        serialized result_data string. Simple but effective for
        deterministic checks.
        """
        if not result_data:
            return {
                "test": f"acceptance: {test_str[:60]}",
                "passed": False,
                "detail": "no result_data to match against",
            }

        # Serialize result to searchable string
        try:
            import json
            serialized = json.dumps(result_data, ensure_ascii=False, default=str)
        except Exception:
            serialized = str(result_data)

        # Extract keywords from test string (words ≥ 3 chars)
        keywords = [
            w.lower()
            for w in re.findall(r"\w+", test_str)
            if len(w) >= 3
        ]

        if not keywords:
            return {
                "test": f"acceptance: {test_str[:60]}",
                "passed": True,
                "detail": "no extractable keywords (auto-pass)",
            }

        serialized_lower = serialized.lower()
        matched = [k for k in keywords if k in serialized_lower]
        match_ratio = len(matched) / len(keywords) if keywords else 1.0

        # Require ≥ 50% keyword match
        passed = match_ratio >= 0.5
        return {
            "test": f"acceptance: {test_str[:60]}",
            "passed": passed,
            "detail": f"{len(matched)}/{len(keywords)} keywords matched ({match_ratio:.0%})",
        }

    @staticmethod
    def _has_material_value(value: Any) -> bool:
        if value is None:
            return False
        if isinstance(value, str):
            return bool(value.strip())
        if isinstance(value, (list, tuple, set, dict)):
            return len(value) > 0
        return True

    def _coerce_acceptance_evidence(
        self,
        parsed_output: Optional[Dict[str, Any]],
    ) -> Optional[Dict[str, Any]]:
        if not parsed_output or not isinstance(parsed_output, dict):
            return None

        acceptance_evidence = parsed_output.get("acceptance_evidence")
        if isinstance(acceptance_evidence, dict) and acceptance_evidence:
            return dict(acceptance_evidence)

        compatibility_evidence = parsed_output.get("pd_storyboard_evidence")
        if isinstance(compatibility_evidence, dict) and compatibility_evidence:
            normalized = dict(compatibility_evidence)
            normalized.setdefault("evidence_kind", "storyboard_preview")
            return normalized

        resolved_outputs = parsed_output.get("resolved_outputs")
        if not isinstance(resolved_outputs, dict):
            return None
        if not any(
            key in resolved_outputs
            for key in ("storyboard", "selected_scene_package_selector")
        ):
            return None

        normalized = {"evidence_kind": "storyboard_preview"}
        for field_name in (
            "session_id",
            "storyboard",
            "storyboard_id",
            "source_type",
            "run_id",
            "status",
            "timeline_items_synced",
            "selected_scene_package_selector",
        ):
            value = resolved_outputs.get(field_name)
            if self._has_material_value(value):
                normalized[field_name] = value

        storyboard = normalized.get("storyboard")
        if isinstance(storyboard, dict) and storyboard.get("storyboard_id"):
            normalized.setdefault("storyboard_id", storyboard["storyboard_id"])

        return normalized if len(normalized) > 1 else None

    def _check_acceptance_evidence(
        self,
        parsed_output: Optional[Dict[str, Any]],
    ) -> Optional[Dict[str, Any]]:
        """Validate generic structured evidence when the sidecar declares it."""
        evidence = self._coerce_acceptance_evidence(parsed_output)
        if not evidence:
            return None

        evidence_kind = str(evidence.get("evidence_kind") or "").strip() or "unknown"
        if evidence_kind != "storyboard_preview":
            return {
                "test": "acceptance_evidence",
                "passed": True,
                "detail": f"unsupported evidence_kind={evidence_kind} (auto-pass)",
            }

        missing_fields: List[str] = []
        storyboard = evidence.get("storyboard")
        storyboard_id = str(evidence.get("storyboard_id") or "").strip()
        if not storyboard_id and isinstance(storyboard, dict):
            storyboard_id = str(storyboard.get("storyboard_id") or "").strip()
        if not storyboard_id:
            missing_fields.append("storyboard_id")

        for field_name in ("session_id", "run_id", "status"):
            value = evidence.get(field_name)
            if not isinstance(value, str) or not value.strip():
                missing_fields.append(field_name)

        status = str(evidence.get("status") or "").strip().lower()
        timeline_items_synced = evidence.get("timeline_items_synced")
        if status and status not in _PREVIEW_SUCCESS_STATUSES:
            missing_fields.append("terminal_success_status")
        if not isinstance(timeline_items_synced, (int, float)) or isinstance(
            timeline_items_synced, bool
        ) or timeline_items_synced < 0:
            missing_fields.append("timeline_items_synced")

        if missing_fields:
            return {
                "test": "acceptance_evidence",
                "passed": False,
                "detail": "missing or invalid acceptance evidence: "
                + ", ".join(missing_fields),
            }

        return {
            "test": "acceptance_evidence",
            "passed": True,
            "detail": (
                f"kind={evidence_kind} session={evidence['session_id']} "
                f"storyboard={storyboard_id} run={evidence['run_id']} "
                f"status={evidence['status']}"
            ),
        }
