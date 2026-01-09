"""
PolicyAttributor（政策歸因器）

職責：把漂移點對應到「哪個治理規則/哪個 lens 介入造成的」
這是 EGB 的第四個元件，負責解釋漂移的原因。
"""

import logging
from typing import List, Optional
from dataclasses import dataclass

from backend.app.egb.schemas.structured_evidence import StructuredEvidence
from backend.app.egb.schemas.drift_report import (
    DriftScores,
    DriftType,
    DriftExplanation,
    AttributionType,
    EvidenceRef,
)

logger = logging.getLogger(__name__)


@dataclass
class PolicyImpact:
    """政策影響記錄"""
    policy_name: str
    impact_type: str           # "blocked" | "modified" | "upgraded"
    description: str
    span_id: Optional[str] = None


class PolicyAttributor:
    """
    政策歸因器

    負責：
    1. 將漂移歸因到具體的治理規則
    2. 識別 Mind-Lens 的影響
    3. 生成人話解釋

    設計原則：
    - 主要使用規則匹配，不需要 LLM
    - 輸出是 DriftExplanation 列表，可用於前端顯示
    """

    # 漂移類型到人話的映射
    DRIFT_TYPE_LABELS = {
        DriftType.EVIDENCE: "檢索來源變更",
        DriftType.PATH: "執行路徑變更",
        DriftType.CONSTRAINT: "約束條件變更",
        DriftType.SEMANTIC: "輸出內容變更",
        DriftType.COST: "成本指標變更",
    }

    def __init__(self):
        """初始化 PolicyAttributor"""
        pass

    async def attribute_drift(
        self,
        drift_scores: DriftScores,
        current_evidence: StructuredEvidence,
        baseline_evidence: StructuredEvidence
    ) -> List[DriftExplanation]:
        """
        歸因漂移來源

        Args:
            drift_scores: 漂移分數
            current_evidence: 當前證據
            baseline_evidence: 基準證據

        Returns:
            DriftExplanation 列表
        """
        explanations = []

        # 處理證據漂移
        if drift_scores.evidence_drift > 0.2:
            explanation = await self._attribute_evidence_drift(
                current_evidence, baseline_evidence, drift_scores.evidence_drift
            )
            if explanation:
                explanations.append(explanation)

        # 處理路徑漂移
        if drift_scores.path_drift > 0.2:
            explanation = await self._attribute_path_drift(
                current_evidence, baseline_evidence, drift_scores.path_drift
            )
            if explanation:
                explanations.append(explanation)

        # 處理約束漂移
        if drift_scores.constraint_drift > 0.2:
            explanation = await self._attribute_constraint_drift(
                current_evidence, baseline_evidence, drift_scores.constraint_drift
            )
            if explanation:
                explanations.append(explanation)

        # 處理語義漂移
        if drift_scores.semantic_drift > 0.2:
            explanation = await self._attribute_semantic_drift(
                current_evidence, baseline_evidence, drift_scores.semantic_drift
            )
            if explanation:
                explanations.append(explanation)

        # 處理成本漂移
        if drift_scores.cost_drift > 0.2:
            explanation = await self._attribute_cost_drift(
                current_evidence, baseline_evidence, drift_scores.cost_drift
            )
            if explanation:
                explanations.append(explanation)

        logger.debug(
            f"PolicyAttributor: Generated {len(explanations)} explanations "
            f"for drift between {current_evidence.run_id} and {baseline_evidence.run_id}"
        )

        return explanations

    async def _attribute_evidence_drift(
        self,
        current: StructuredEvidence,
        baseline: StructuredEvidence,
        score: float
    ) -> Optional[DriftExplanation]:
        """歸因證據漂移"""
        current_sources = set(current.retrieval_evidence.sources)
        baseline_sources = set(baseline.retrieval_evidence.sources)

        new_sources = current_sources - baseline_sources
        removed_sources = baseline_sources - current_sources

        if new_sources or removed_sources:
            explanation_parts = []
            if new_sources:
                explanation_parts.append(f"新增來源: {', '.join(list(new_sources)[:3])}")
            if removed_sources:
                explanation_parts.append(f"移除來源: {', '.join(list(removed_sources)[:3])}")

            explanation = "; ".join(explanation_parts)

            return DriftExplanation(
                drift_type=DriftType.EVIDENCE,
                explanation=f"檢索來源發生變更。{explanation}",
                severity=self._score_to_severity(score),
                impact="可能影響回答的資訊基礎",
                attribution_type=AttributionType.DATA,
                attributed_to="retrieval_sources",
            )

        # 來源相同但 chunks 不同
        return DriftExplanation(
            drift_type=DriftType.EVIDENCE,
            explanation="檢索到的內容片段發生變更，但來源相同",
            severity=self._score_to_severity(score),
            impact="回答的細節可能有所不同",
            attribution_type=AttributionType.DATA,
            attributed_to="retrieval_chunks",
        )

    async def _attribute_path_drift(
        self,
        current: StructuredEvidence,
        baseline: StructuredEvidence,
        score: float
    ) -> Optional[DriftExplanation]:
        """歸因路徑漂移"""
        current_path = current.tool_path.tool_names
        baseline_path = baseline.tool_path.tool_names

        # 分析路徑差異
        if len(current_path) != len(baseline_path):
            diff = len(current_path) - len(baseline_path)
            if diff > 0:
                explanation = f"執行路徑變長，增加了 {diff} 個步驟"
            else:
                explanation = f"執行路徑變短，減少了 {-diff} 個步驟"
        else:
            # 長度相同，但工具不同
            diff_count = sum(1 for a, b in zip(current_path, baseline_path) if a != b)
            explanation = f"執行路徑中有 {diff_count} 個步驟使用了不同的工具"

        # 檢查是否因政策導致
        if current.has_strictness_escalation or any(
            not p.passed for p in current.policy_checks
        ):
            attribution_type = AttributionType.POLICY
            attributed_to = "governance_policy"
            explanation += "（可能受到政策約束影響）"
        else:
            attribution_type = AttributionType.MODEL
            attributed_to = "model_decision"

        return DriftExplanation(
            drift_type=DriftType.PATH,
            explanation=explanation,
            severity=self._score_to_severity(score),
            impact="執行流程發生變化，可能影響結果",
            attribution_type=attribution_type,
            attributed_to=attributed_to,
        )

    async def _attribute_constraint_drift(
        self,
        current: StructuredEvidence,
        baseline: StructuredEvidence,
        score: float
    ) -> Optional[DriftExplanation]:
        """歸因約束漂移"""
        explanations_parts = []
        evidence_refs = []

        # 檢查嚴謹度變更
        if current.final_strictness_level != baseline.final_strictness_level:
            diff = current.final_strictness_level - baseline.final_strictness_level
            if diff > 0:
                explanations_parts.append(
                    f"嚴謹度從 Level {baseline.final_strictness_level} 升級到 Level {current.final_strictness_level}"
                )
            else:
                explanations_parts.append(
                    f"嚴謹度從 Level {baseline.final_strictness_level} 降級到 Level {current.final_strictness_level}"
                )

        # 檢查政策檢查結果
        current_failed = [p for p in current.policy_checks if not p.passed]
        baseline_failed = [p for p in baseline.policy_checks if not p.passed]

        if len(current_failed) != len(baseline_failed):
            if len(current_failed) > len(baseline_failed):
                new_failures = len(current_failed) - len(baseline_failed)
                explanations_parts.append(f"新增 {new_failures} 個政策約束未通過")
            else:
                fixed_failures = len(baseline_failed) - len(current_failed)
                explanations_parts.append(f"修復了 {fixed_failures} 個政策約束問題")

        # 添加嚴謹度變更的證據引用
        for change in current.strictness_changes:
            if change.span_id:
                evidence_refs.append(EvidenceRef(
                    ref_type="span",
                    ref_id=change.span_id,
                    description=f"嚴謹度變更: {change.from_level} → {change.to_level}"
                ))

        if not explanations_parts:
            explanations_parts.append("治理約束條件發生變更")

        return DriftExplanation(
            drift_type=DriftType.CONSTRAINT,
            explanation="。".join(explanations_parts),
            severity=self._score_to_severity(score),
            impact="執行的約束條件改變，可能影響行為一致性",
            attribution_type=AttributionType.POLICY,
            attributed_to="governance_constraints",
            evidence_refs=evidence_refs,
        )

    async def _attribute_semantic_drift(
        self,
        current: StructuredEvidence,
        baseline: StructuredEvidence,
        score: float
    ) -> Optional[DriftExplanation]:
        """歸因語義漂移"""
        # 分析輸出差異
        length_diff = current.output_length - baseline.output_length
        length_change = abs(length_diff) / max(baseline.output_length, 1) * 100

        explanation_parts = []

        if length_change > 20:
            if length_diff > 0:
                explanation_parts.append(f"輸出長度增加了約 {length_change:.0f}%")
            else:
                explanation_parts.append(f"輸出長度減少了約 {length_change:.0f}%")

        # 檢查關鍵主張差異
        # ⚠️ P0-5：已移除 key_assertions，改用 key_fields_hash_map
        if current.key_fields_hash_map and baseline.key_fields_hash_map:
            current_keys = set(current.key_fields_hash_map.keys())
            baseline_keys = set(baseline.key_fields_hash_map.keys())
            current_set = current_keys
            baseline_set = baseline_keys

            new_assertions = current_set - baseline_set
            removed_assertions = baseline_set - current_set

            if new_assertions:
                explanation_parts.append(f"新增主張: {len(new_assertions)} 個")
            if removed_assertions:
                explanation_parts.append(f"移除主張: {len(removed_assertions)} 個")

        if not explanation_parts:
            explanation_parts.append("輸出內容與上次不同")

        # 判斷歸因
        if score > 0.7:
            attribution_type = AttributionType.UNKNOWN
            impact = "輸出內容發生重大變化，需要檢查是否符合預期"
        else:
            attribution_type = AttributionType.MODEL
            impact = "輸出內容有所調整，可能是正常變化"

        return DriftExplanation(
            drift_type=DriftType.SEMANTIC,
            explanation="。".join(explanation_parts),
            severity=self._score_to_severity(score),
            impact=impact,
            attribution_type=attribution_type,
            attributed_to="output_content",
        )

    async def _attribute_cost_drift(
        self,
        current: StructuredEvidence,
        baseline: StructuredEvidence,
        score: float
    ) -> Optional[DriftExplanation]:
        """歸因成本漂移"""
        explanation_parts = []

        # Token 變化
        if baseline.metrics.total_tokens > 0:
            token_change = (current.metrics.total_tokens - baseline.metrics.total_tokens) / baseline.metrics.total_tokens * 100
            if abs(token_change) > 20:
                if token_change > 0:
                    explanation_parts.append(f"Token 使用量增加 {token_change:.0f}%")
                else:
                    explanation_parts.append(f"Token 使用量減少 {-token_change:.0f}%")

        # 延遲變化
        if baseline.metrics.total_latency_ms > 0:
            latency_change = (current.metrics.total_latency_ms - baseline.metrics.total_latency_ms) / baseline.metrics.total_latency_ms * 100
            if abs(latency_change) > 20:
                if latency_change > 0:
                    explanation_parts.append(f"執行時間增加 {latency_change:.0f}%")
                else:
                    explanation_parts.append(f"執行時間減少 {-latency_change:.0f}%")

        # 錯誤率變化
        current_errors = current.metrics.error_count
        baseline_errors = baseline.metrics.error_count

        if current_errors != baseline_errors:
            if current_errors > baseline_errors:
                explanation_parts.append(f"錯誤次數從 {baseline_errors} 增加到 {current_errors}")
            else:
                explanation_parts.append(f"錯誤次數從 {baseline_errors} 減少到 {current_errors}")

        if not explanation_parts:
            explanation_parts.append("執行成本指標發生變化")

        return DriftExplanation(
            drift_type=DriftType.COST,
            explanation="。".join(explanation_parts),
            severity=self._score_to_severity(score),
            impact="執行效率或成本發生變化",
            attribution_type=AttributionType.MODEL,
            attributed_to="execution_metrics",
        )

    async def identify_policy_impacts(
        self,
        evidence: StructuredEvidence
    ) -> List[PolicyImpact]:
        """
        識別證據中的政策影響

        Args:
            evidence: 結構化證據

        Returns:
            PolicyImpact 列表
        """
        impacts = []

        # 從政策檢查中提取影響
        for check in evidence.policy_checks:
            if not check.passed:
                impacts.append(PolicyImpact(
                    policy_name=check.policy_name,
                    impact_type="blocked",
                    description=check.reason or f"{check.check_type} 檢查未通過",
                    span_id=check.span_id,
                ))

        # 從嚴謹度變更中提取影響
        for change in evidence.strictness_changes:
            if change.to_level > change.from_level:
                impacts.append(PolicyImpact(
                    policy_name=f"strictness_level_{change.to_level}",
                    impact_type="upgraded",
                    description=f"嚴謹度升級: {change.reason}",
                    span_id=change.span_id,
                ))

        return impacts

    def _score_to_severity(self, score: float) -> str:
        """將分數轉換為嚴重程度"""
        if score < 0.3:
            return "low"
        elif score < 0.6:
            return "medium"
        else:
            return "high"

