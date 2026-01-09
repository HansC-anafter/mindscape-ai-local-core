"""
DriftScorer (Drift Scorer)

Responsibilities: Calculate five types of drift scores
- Evidence drift (evidence_drift): Retrieval chunks differences
- Path drift (path_drift): Tool call sequence differences
- Constraint drift (constraint_drift): Policy/strictness changes
- Semantic drift (semantic_drift): Output claim differences
- Cost drift (cost_drift): Token/time/error rate differences
"""

import logging
from typing import Optional, List, Set
from difflib import SequenceMatcher

from backend.app.egb.schemas.structured_evidence import StructuredEvidence
from backend.app.egb.schemas.drift_report import DriftScores, DriftType

logger = logging.getLogger(__name__)


class DriftScorer:
    """
    Drift scorer

    Responsible for calculating multi-dimensional drift scores between two StructuredEvidence.
    All calculations are pure math/rule-based, no LLM usage.
    """

    # Cost drift thresholds
    COST_DRIFT_THRESHOLD_TOKEN = 0.5      # Token difference > 50% considered significant
    COST_DRIFT_THRESHOLD_LATENCY = 0.5    # Latency difference > 50% considered significant
    COST_DRIFT_THRESHOLD_ERROR = 0.1      # Error rate difference > 10% considered significant

    def __init__(self):
        """Initialize DriftScorer"""
        pass

    async def compute_drift(
        self,
        current: StructuredEvidence,
        baseline: StructuredEvidence,
        store=None,  # New: For external_job_drift status queries
    ) -> DriftScores:
        """
        Calculate drift of current evidence relative to baseline

        Args:
            current: Structured evidence from current run
            baseline: Structured evidence from baseline run
            store: Optional store (for querying ExternalJobMapping status)

        Returns:
            DriftScores: Drift scores for each dimension
        """
        scores = DriftScores(
            evidence_drift=await self.compute_evidence_drift(current, baseline),
            path_drift=await self.compute_path_drift(current, baseline),
            constraint_drift=await self.compute_constraint_drift(current, baseline),
            semantic_drift=await self.compute_semantic_drift(current, baseline),
            cost_drift=await self.compute_cost_drift(current, baseline),
            external_job_drift=await self.compute_external_job_drift(current, baseline, store=store),  # ⚠️ P0-8
        )

        logger.debug(
            f"DriftScorer: Computed drift between {current.run_id} and {baseline.run_id}: "
            f"overall={scores.overall_score:.2f}, level={scores.level.value}"
        )

        return scores

    async def compute_evidence_drift(
        self,
        current: StructuredEvidence,
        baseline: StructuredEvidence
    ) -> float:
        """
        Calculate evidence drift

        Calculate retrieval chunks differences based on Jaccard similarity.
        """
        current_chunks = set(current.retrieval_evidence.chunk_ids)
        baseline_chunks = set(baseline.retrieval_evidence.chunk_ids)

        if not current_chunks and not baseline_chunks:
            return 0.0  # No retrievals, considered no drift

        # Jaccard distance = 1 - Jaccard similarity
        intersection = len(current_chunks & baseline_chunks)
        union = len(current_chunks | baseline_chunks)

        if union == 0:
            return 0.0

        jaccard_similarity = intersection / union
        return 1.0 - jaccard_similarity

    async def compute_path_drift(
        self,
        current: StructuredEvidence,
        baseline: StructuredEvidence
    ) -> float:
        """
        Calculate path drift

        ⚠️ P0-5 硬規則：v1 固定算法（完全不用 embedding）

        算法：tool_name sequence 的 normalized edit distance
        - current_seq = current.tool_path（例如：["search", "fetch", "format"]）
        - baseline_seq = baseline.tool_path
        - 計算 Levenshtein distance
        - normalized = distance / max(len(current_seq), len(baseline_seq), 1)

        ⚠️ P0-5：雙模式計算（ordered vs. bag）
        - ordered_path_drift：Levenshtein（序列敏感）
        - bag_path_drift：multiset 差（序列不敏感，用於並行執行）
        - 最終取 min(ordered, bag)（避免並行執行被誤判為高漂移）

        ⚠️ P0-8 擴展：包含 EXTERNAL_JOB 節點（tool_path 已包含）

        Returns:
            float: 0.0（完全相同）~ 1.0（完全不同）
        """
        current_path = current.tool_path.tool_names
        baseline_path = baseline.tool_path.tool_names

        if not current_path and not baseline_path:
            return 0.0  # No tool calls, considered no drift

        # Mode 1: ordered_path_drift (sequence-sensitive)
        matcher = SequenceMatcher(None, current_path, baseline_path)
        ordered_similarity = matcher.ratio()
        ordered_drift = 1.0 - ordered_similarity

        # Mode 2: bag_path_drift (sequence-insensitive, for parallel execution)
        from collections import Counter
        current_counter = Counter(current_path)
        baseline_counter = Counter(baseline_path)

        all_tools = set(current_path) | set(baseline_path)
        if not all_tools:
            bag_drift = 0.0
        else:
            diff_count = sum(
                abs(current_counter.get(tool, 0) - baseline_counter.get(tool, 0))
                for tool in all_tools
            )
            total_count = sum(current_counter.values()) + sum(baseline_counter.values())
            bag_drift = diff_count / max(total_count, 1)

        # Take smaller value (conservative, avoid misclassifying parallel execution as high drift)
        return min(ordered_drift, bag_drift)

    async def compute_constraint_drift(
        self,
        current: StructuredEvidence,
        baseline: StructuredEvidence
    ) -> float:
        """
        計算約束漂移

        ⚠️ P0-5 硬規則：v1 固定算法（規則表打分）

        算法：規則表打分（完全不用 embedding）
        - strictness 變化：|current.strictness_level - baseline.strictness_level| / 3.0
        - policy_version 變化：不同版本 = 0.5，相同 = 0.0
        - lens_level 變化：|current.mind_lens_level - baseline.mind_lens_level| / 3.0
        - 加權平均：strictness(0.4) + policy(0.4) + lens(0.2)

        Returns:
            float: 0.0（完全相同）~ 1.0（完全不同）
        """
        drift_factors = []

        # Compare strictness levels
        current_strictness = current.strictness_level
        baseline_strictness = baseline.strictness_level
        strictness_diff = abs(current_strictness - baseline_strictness) / 3.0

        # 比較 policy_version
        policy_diff = 0.5 if current.policy_version != baseline.policy_version else 0.0

        # Compare lens_level
        lens_diff = abs(current.mind_lens_level - baseline.mind_lens_level) / 3.0

        # Weighted average
        constraint_drift = (
            strictness_diff * 0.4 +
            policy_diff * 0.4 +
            lens_diff * 0.2
        )

        return min(constraint_drift, 1.0)  # clamp 到 0~1

    async def compute_semantic_drift(
        self,
        current: StructuredEvidence,
        baseline: StructuredEvidence
    ) -> float:
        """
        Calculate semantic drift

        Design principles:
        - When strictness ≥ 1, use JSON Pointer whitelist to compare structured output
        - When strictness = 0, only use output_hash (rough)
        - No LLM extraction dependency, ensure controllable, verifiable, explainable

        Note: key_fields_diff should be pre-calculated by EvidenceReducer based on JSON schema.
        """
        # Fast path: same hash means no drift
        if current.output_hash == baseline.output_hash:
            return 0.0

        # Get strictness level (from metadata or evidence)
        strictness = current.final_strictness_level

        if strictness >= 1:
            # ===== 結構化輸出模式 =====
            # Use key_fields_diff to compare key fields
            return self._compute_structured_semantic_drift(current, baseline)
        else:
            # ===== 粗略模式（strictness = 0）=====
            return self._compute_rough_semantic_drift(current, baseline)

    def _compute_structured_semantic_drift(
        self,
        current: StructuredEvidence,
        baseline: StructuredEvidence
    ) -> float:
        """
        計算結構化輸出的語義漂移

        ⚠️ P0-5 硬規則：v1 固定算法（完全不用 embedding）

        算法：key_fields_hash 是否一致
        - 若 current.key_fields_hash == baseline.key_fields_hash：drift = 0.0
        - 若不一致：
          - 計算 key_fields_diff_count（key_fields_hash_map 中不同的 pointer 數量）
          - total_key_fields = len(union(current.key_fields_hash_map.keys(), baseline.key_fields_hash_map.keys()))
          - drift = key_fields_diff_count / max(total_key_fields, 1)

        ⚠️ v1.2.2 修正：使用 effective_strictness 處理 strictness 不一致
        effective_strictness = min(current.strictness_level, baseline.strictness_level)
        """
        # ⚠️ v1.2.2：使用 effective_strictness
        effective_strictness = min(
            current.strictness_level,
            baseline.strictness_level
        )

        if effective_strictness < 1:
            # If effective_strictness < 1, fallback to rough mode
            return self._compute_rough_semantic_drift(current, baseline)

        # Calculate using key_fields_hash_map
        if not current.key_fields_hash_map or not baseline.key_fields_hash_map:
            # If no hash_map, fallback to hash comparison
            if current.key_fields_hash and baseline.key_fields_hash:
                return 0.0 if current.key_fields_hash == baseline.key_fields_hash else 1.0
            return self._compute_rough_semantic_drift(current, baseline)

        # Count different pointers
        current_keys = set(current.key_fields_hash_map.keys())
        baseline_keys = set(baseline.key_fields_hash_map.keys())

        # Find different pointers
        diff_pointers = []
        all_keys = current_keys | baseline_keys

        for key in all_keys:
            current_hash = current.key_fields_hash_map.get(key)
            baseline_hash = baseline.key_fields_hash_map.get(key)
            if current_hash != baseline_hash:
                diff_pointers.append(key)

        # Calculate drift
        total_key_fields = len(all_keys)
        if total_key_fields == 0:
            return 0.0

        drift = len(diff_pointers) / total_key_fields
        return min(drift, 1.0)  # clamp 到 0~1

    def _compute_rough_semantic_drift(
        self,
        current: StructuredEvidence,
        baseline: StructuredEvidence
    ) -> float:
        """
        Rough semantic drift calculation (strictness = 0)

        Only use hash and length, don't attempt fine-grained analysis.
        """
        # Hash already different, base score 0.3
        drift = 0.3

        # Length difference as supplement
        if current.output_length > 0 and baseline.output_length > 0:
            length_ratio = min(current.output_length, baseline.output_length) / max(current.output_length, baseline.output_length)
            if length_ratio < 0.7:
                # Significant length difference
                drift += (1.0 - length_ratio) * 0.3

        return min(drift, 0.7)  # Rough mode max 0.7, avoid over-alerting

    async def compute_cost_drift(
        self,
        current: StructuredEvidence,
        baseline: StructuredEvidence
    ) -> float:
        """
        成本漂移：token/latency 的比例差

        ⚠️ P0-5 硬規則：v1 固定算法（完全不用 embedding）

        算法：token/latency 的比例差（clamp 到 0~1）
        - 優先使用 Langfuse cost（基於 model pricing）
        - 若沒有 cost，fallback 到 token_drift：
          - current_tokens = current.total_tokens
          - baseline_tokens = baseline.total_tokens
          - ratio = abs(current_tokens - baseline_tokens) / max(baseline_tokens, 1)
          - drift = min(ratio, 1.0)  # clamp 到 0~1
        - 若都沒有：drift = 0.0

        Returns:
            float: 0.0（完全相同）~ 1.0（完全不同）
        """
        # Prefer Langfuse cost
        if current.metrics.total_cost_usd > 0 and baseline.metrics.total_cost_usd > 0:
            cost_ratio = abs(
                current.metrics.total_cost_usd - baseline.metrics.total_cost_usd
            ) / max(baseline.metrics.total_cost_usd, 0.01)
            return min(cost_ratio, 1.0)

        # Fallback 到 token_drift
        if current.metrics.total_tokens > 0 and baseline.metrics.total_tokens > 0:
            token_ratio = abs(
                current.metrics.total_tokens - baseline.metrics.total_tokens
            ) / max(baseline.metrics.total_tokens, 1)
            return min(token_ratio, 1.0)

        # If neither available: drift = 0.0
        return 0.0

    async def compute_external_job_drift(
        self,
        current: StructuredEvidence,
        baseline: StructuredEvidence,
        store=None,  # New: For querying ExternalJobMapping status
    ) -> float:
        """
        Calculate external workflow drift (P0-8 addition)

        P0-8 hard rule: v1 fixed algorithm (improved version)

        Algorithm (multi-dimensional comparison):
        1. Tool name sequence difference (Jaccard distance)
        2. Output fingerprint difference (if both available)
        3. Status difference (if available from store)

        Returns:
            float: 0.0 (identical) ~ 1.0 (completely different)
        """
        # Extract external_job related tools from tool_path
        current_external_tools = [
            name for name in current.tool_path.tool_names
            if any(keyword in name.lower() for keyword in ["external", "n8n", "zapier", "make", "webhook"])
        ]
        baseline_external_tools = [
            name for name in baseline.tool_path.tool_names
            if any(keyword in name.lower() for keyword in ["external", "n8n", "zapier", "make", "webhook"])
        ]

        # If no external jobs, return 0.0
        if not current_external_tools and not baseline_external_tools:
            return 0.0

        drift_factors = []

        # 1. 工具名序列差異（Jaccard 距離）
        current_set = set(current_external_tools)
        baseline_set = set(baseline_external_tools)
        intersection = len(current_set & baseline_set)
        union = len(current_set | baseline_set)
        if union > 0:
            tool_name_drift = 1.0 - (intersection / union)
            drift_factors.append(("tool_name", tool_name_drift, 0.4))  # Weight 40%

        # 2. 輸出指紋差異（如果可從 store 獲取）
        if store:
            try:
                from backend.app.egb.stores.evidence_profile_store import EvidenceProfileStore
                if isinstance(store, EvidenceProfileStore):
                    current_jobs = await store.get_external_jobs_by_run(current.run_id)
                    baseline_jobs = await store.get_external_jobs_by_run(baseline.run_id)

                    # Compare status differences
                    current_statuses = {job.status for job in current_jobs}
                    baseline_statuses = {job.status for job in baseline_jobs}
                    if current_statuses or baseline_statuses:
                        status_intersection = len(current_statuses & baseline_statuses)
                        status_union = len(current_statuses | baseline_statuses)
                        if status_union > 0:
                            status_drift = 1.0 - (status_intersection / status_union)
                            drift_factors.append(("status", status_drift, 0.3))  # Weight 30%

                    # Compare output_fingerprint (if available)
                    # Note: output_fingerprint needs to be extracted from ExternalJobMapping or trace
                    # Currently ExternalJobMapping has no output_fingerprint field, needs extension
            except Exception as e:
                logger.warning(f"DriftScorer: Failed to get external job status from store: {e}")

        # If no other factors, only use tool name difference
        if not drift_factors:
            return tool_name_drift if 'tool_name_drift' in locals() else 0.0

        # Weighted average
        total_weight = sum(weight for _, _, weight in drift_factors)
        if total_weight == 0:
            return 0.0

        weighted_drift = sum(drift * weight for _, drift, weight in drift_factors) / total_weight
        return min(weighted_drift, 1.0)  # clamp 到 0~1

    def _compute_error_rate(self, evidence: StructuredEvidence) -> float:
        """計算錯誤率"""
        total_calls = evidence.metrics.llm_calls + evidence.metrics.tool_calls
        if total_calls == 0:
            return 0.0
        return evidence.metrics.error_count / total_calls

    async def identify_dominant_drifts(
        self,
        scores: DriftScores,
        threshold: float = 0.3
    ) -> List[DriftType]:
        """
        識別顯著的漂移類型

        Args:
            scores: 漂移分數
            threshold: 閾值，超過此值視為顯著

        Returns:
            顯著漂移類型列表（按嚴重程度排序）
        """
        drifts = []

        if scores.evidence_drift >= threshold:
            drifts.append((DriftType.EVIDENCE, scores.evidence_drift))
        if scores.path_drift >= threshold:
            drifts.append((DriftType.PATH, scores.path_drift))
        if scores.constraint_drift >= threshold:
            drifts.append((DriftType.CONSTRAINT, scores.constraint_drift))
        if scores.semantic_drift >= threshold:
            drifts.append((DriftType.SEMANTIC, scores.semantic_drift))
        if scores.cost_drift >= threshold:
            drifts.append((DriftType.COST, scores.cost_drift))

        # Sort by severity
        drifts.sort(key=lambda x: x[1], reverse=True)

        return [d[0] for d in drifts]

