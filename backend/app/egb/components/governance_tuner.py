"""
GovernanceTuner（治理調參器）

職責：產生可執行的建議（strictness 升級、toolset 收斂、scope 鎖定等）
並回寫成 DecisionRecord（決策紀錄）
這是 EGB 的第六個元件，負責產生治理處方並執行。
"""

import logging
from typing import Optional, List, Dict, Any
from datetime import datetime, timedelta
from dataclasses import dataclass
import uuid

from backend.app.egb.schemas.drift_report import (
    RunDriftReport,
    DriftExplanation,
    DriftType,
    DriftLevel,
)
from backend.app.egb.schemas.governance_prescription import (
    GovernancePrescription,
    TunerRecommendation,
    GovernanceAction,
    ExpectedOutcome,
    RiskAssessment,
    KnobType,
    ActionType,
)
from backend.app.egb.schemas.decision_record import (
    DecisionRecord,
    DecisionType,
    DecisionSource,
)

logger = logging.getLogger(__name__)


@dataclass
class GovernanceSettings:
    """當前治理設定"""
    strictness_level: int = 0
    allowed_tools: List[str] = None
    denied_tools: List[str] = None
    scope_locked: bool = False
    verifier_enabled: bool = False
    consistency_mode: bool = False
    cost_limit_usd: float = 0.0

    def __post_init__(self):
        if self.allowed_tools is None:
            self.allowed_tools = []
        if self.denied_tools is None:
            self.denied_tools = []


@dataclass
class ApplyResult:
    """套用處方的結果"""
    success: bool
    applied_actions: List[str]
    failed_actions: List[str]
    decision_record: Optional[DecisionRecord] = None
    error: Optional[str] = None


class GovernanceTuner:
    """
    治理調參器

    負責：
    1. 根據漂移報告生成治理處方
    2. 提供一鍵套用功能
    3. 記錄決策到 DecisionRecord

    設計原則：
    - 主要使用規則生成建議
    - 複雜場景可選擇性使用 LLM
    - 所有決策都要記錄
    """

    # 嚴謹度升級閾值
    STRICTNESS_UPGRADE_THRESHOLD = {
        DriftLevel.MILD: 0,       # 輕微漂移不升級
        DriftLevel.MODERATE: 1,   # 中度漂移升級 1 級
        DriftLevel.HIGH: 2,       # 高度漂移升級 2 級
    }

    def __init__(self, settings_store=None):
        """
        初始化 GovernanceTuner

        Args:
            settings_store: 治理設定存儲（可選）
        """
        self.settings_store = settings_store

    async def generate_prescription(
        self,
        drift_report: RunDriftReport,
        attribution: List[DriftExplanation],
        current_settings: GovernanceSettings
    ) -> GovernancePrescription:
        """
        生成治理處方

        Args:
            drift_report: 漂移報告
            attribution: 漂移歸因列表
            current_settings: 當前治理設定

        Returns:
            GovernancePrescription: 治理處方
        """
        prescription = GovernancePrescription(
            prescription_id=str(uuid.uuid4()),
            intent_id=drift_report.intent_id,
            run_id=drift_report.run_id,
            workspace_id=drift_report.workspace_id,
            created_at=datetime.utcnow(),
            expires_at=datetime.utcnow() + timedelta(hours=24),
        )

        # 根據漂移類型生成建議
        recommendations = []
        actions = []
        expected_outcomes = []

        # 處理整體漂移等級
        if drift_report.drift_level in [DriftLevel.MODERATE, DriftLevel.HIGH]:
            strictness_rec = self._generate_strictness_recommendation(
                drift_report, current_settings
            )
            if strictness_rec:
                recommendations.append(strictness_rec)
                actions.extend(
                    self._create_strictness_actions(strictness_rec, current_settings)
                )

        # 處理各類漂移
        for explanation in attribution:
            rec = self._generate_recommendation_for_drift(
                explanation, current_settings
            )
            if rec:
                recommendations.append(rec)

        # 生成預期效果
        expected_outcomes = self._generate_expected_outcomes(
            recommendations, drift_report
        )

        # 生成風險評估
        risk_assessment = self._assess_risk(recommendations, drift_report)

        prescription.recommendations = recommendations
        prescription.applicable_actions = actions
        prescription.expected_outcomes = expected_outcomes
        prescription.risk_assessment = risk_assessment
        prescription.confidence = self._calculate_confidence(recommendations)

        logger.info(
            f"GovernanceTuner: Generated prescription {prescription.prescription_id} "
            f"with {len(recommendations)} recommendations for run {drift_report.run_id}"
        )

        return prescription

    async def apply_prescription(
        self,
        prescription: GovernancePrescription,
        workspace_id: str,
        user_id: str = "system"
    ) -> ApplyResult:
        """
        套用治理處方（一鍵調整）

        Args:
            prescription: 治理處方
            workspace_id: 工作空間 ID
            user_id: 執行者 ID

        Returns:
            ApplyResult: 套用結果
        """
        applied_actions = []
        failed_actions = []

        for action in prescription.applicable_actions:
            try:
                await self._apply_action(action, workspace_id)
                applied_actions.append(action.action_id)
            except Exception as e:
                logger.error(f"Failed to apply action {action.action_id}: {e}")
                failed_actions.append(action.action_id)

        success = len(failed_actions) == 0

        # 記錄決策
        decision_record = await self.record_decision(
            prescription=prescription,
            applied=success,
            user_id=user_id,
            applied_actions=applied_actions,
            failed_actions=failed_actions,
        )

        # 更新處方狀態
        prescription.status = "applied" if success else "partially_applied"
        prescription.applied_at = datetime.utcnow()
        prescription.applied_by = user_id

        return ApplyResult(
            success=success,
            applied_actions=applied_actions,
            failed_actions=failed_actions,
            decision_record=decision_record,
        )

    async def record_decision(
        self,
        prescription: GovernancePrescription,
        applied: bool,
        user_id: str,
        applied_actions: List[str] = None,
        failed_actions: List[str] = None,
    ) -> DecisionRecord:
        """
        記錄決策

        Args:
            prescription: 治理處方
            applied: 是否已套用
            user_id: 決策者 ID
            applied_actions: 已套用的動作
            failed_actions: 失敗的動作

        Returns:
            DecisionRecord: 決策記錄
        """
        record = DecisionRecord(
            record_id=str(uuid.uuid4()),
            decision_type=DecisionType.PRESCRIPTION_APPLIED,
            decision_source=(
                DecisionSource.USER_MANUAL
                if user_id != "system"
                else DecisionSource.EGB_PRESCRIPTION
            ),
            workspace_id=prescription.workspace_id,
            intent_id=prescription.intent_id,
            run_id=prescription.run_id,
            prescription_id=prescription.prescription_id,
            decision_summary=self._generate_decision_summary(prescription, applied),
            changes_made={
                "recommendations": [r.to_dict() for r in prescription.recommendations],
                "applied_actions": applied_actions or [],
                "failed_actions": failed_actions or [],
            },
            rationale=self._generate_rationale(prescription),
            decided_by=user_id,
            decided_at=datetime.utcnow(),
            status="executed" if applied else "failed",
        )

        # 添加證據連結
        record.add_evidence(
            evidence_type="prescription",
            evidence_id=prescription.prescription_id,
            description="治理處方"
        )

        logger.info(
            f"GovernanceTuner: Recorded decision {record.record_id} "
            f"for prescription {prescription.prescription_id}"
        )

        return record

    def _generate_strictness_recommendation(
        self,
        drift_report: RunDriftReport,
        current_settings: GovernanceSettings
    ) -> Optional[TunerRecommendation]:
        """生成嚴謹度調整建議"""
        upgrade_amount = self.STRICTNESS_UPGRADE_THRESHOLD.get(
            drift_report.drift_level, 0
        )

        if upgrade_amount == 0:
            return None

        new_level = min(current_settings.strictness_level + upgrade_amount, 3)

        if new_level == current_settings.strictness_level:
            return None

        return TunerRecommendation(
            knob_type=KnobType.STRICTNESS,
            knob_name="嚴謹度等級",
            current_value=current_settings.strictness_level,
            suggested_value=new_level,
            rationale=f"漂移等級為 {drift_report.drift_level.value}，建議提高嚴謹度以增加穩定性",
            expected_impact="執行更加穩定，但可能增加延遲和成本",
            priority="high" if upgrade_amount >= 2 else "medium",
            risk_if_ignored="high" if drift_report.drift_level == DriftLevel.HIGH else "medium",
        )

    def _generate_recommendation_for_drift(
        self,
        explanation: DriftExplanation,
        current_settings: GovernanceSettings
    ) -> Optional[TunerRecommendation]:
        """根據漂移類型生成建議"""
        if explanation.drift_type == DriftType.EVIDENCE:
            # 建議鎖定資料範圍
            if not current_settings.scope_locked:
                return TunerRecommendation(
                    knob_type=KnobType.SCOPE,
                    knob_name="資料範圍鎖定",
                    current_value=False,
                    suggested_value=True,
                    rationale="檢索來源變更導致漂移，建議鎖定資料範圍",
                    expected_impact="回答將基於固定的資料來源",
                    priority=explanation.severity,
                )

        elif explanation.drift_type == DriftType.PATH:
            # 建議啟用一致性模式
            if not current_settings.consistency_mode:
                return TunerRecommendation(
                    knob_type=KnobType.CONSISTENCY_MODE,
                    knob_name="一致性模式",
                    current_value=False,
                    suggested_value=True,
                    rationale="執行路徑變更導致漂移，建議啟用一致性模式",
                    expected_impact="執行路徑將更加穩定",
                    priority=explanation.severity,
                )

        elif explanation.drift_type == DriftType.SEMANTIC:
            # 建議啟用驗證器
            if not current_settings.verifier_enabled:
                return TunerRecommendation(
                    knob_type=KnobType.VERIFIER,
                    knob_name="輸出驗證器",
                    current_value=False,
                    suggested_value=True,
                    rationale="輸出內容變更導致漂移，建議啟用驗證器",
                    expected_impact="輸出將經過額外驗證，提高一致性",
                    priority=explanation.severity,
                )

        return None

    def _create_strictness_actions(
        self,
        recommendation: TunerRecommendation,
        current_settings: GovernanceSettings
    ) -> List[GovernanceAction]:
        """創建嚴謹度調整的動作"""
        actions = []

        new_level = recommendation.suggested_value

        actions.append(GovernanceAction(
            action_type=ActionType.SET,
            target_knob=KnobType.STRICTNESS,
            target_value=new_level,
            label=f"提高嚴謹度到 Level {new_level}",
            description=f"將嚴謹度從 {current_settings.strictness_level} 調整到 {new_level}",
            requires_confirmation=new_level >= 2,
            confirmation_message=(
                f"確定要將嚴謹度提高到 Level {new_level}？這可能會增加執行時間和成本。"
                if new_level >= 2 else None
            ),
        ))

        return actions

    def _generate_expected_outcomes(
        self,
        recommendations: List[TunerRecommendation],
        drift_report: RunDriftReport
    ) -> List[ExpectedOutcome]:
        """生成預期效果"""
        outcomes = []

        # 穩定性改善
        if recommendations:
            outcomes.append(ExpectedOutcome(
                outcome_type="stability",
                direction="improve",
                magnitude="moderate" if len(recommendations) > 1 else "slight",
                description="執行結果的一致性將提高",
            ))

        # 成本影響
        strictness_recs = [
            r for r in recommendations if r.knob_type == KnobType.STRICTNESS
        ]
        if strictness_recs:
            outcomes.append(ExpectedOutcome(
                outcome_type="cost",
                direction="increase" if strictness_recs[0].suggested_value > strictness_recs[0].current_value else "neutral",
                magnitude="slight",
                description="可能略微增加執行成本和時間",
            ))

        return outcomes

    def _assess_risk(
        self,
        recommendations: List[TunerRecommendation],
        drift_report: RunDriftReport
    ) -> RiskAssessment:
        """評估風險"""
        risk_factors = []
        mitigations = []

        # 評估各建議的風險
        for rec in recommendations:
            if rec.risk_if_applied == "high":
                risk_factors.append(f"{rec.knob_name} 調整可能帶來副作用")
                mitigations.append(f"建議先在測試環境驗證 {rec.knob_name} 的調整")

        # 整體風險
        high_risk_count = sum(1 for r in recommendations if r.risk_if_applied == "high")

        if high_risk_count >= 2:
            overall_risk = "high"
        elif high_risk_count == 1 or len(recommendations) >= 3:
            overall_risk = "medium"
        else:
            overall_risk = "low"

        return RiskAssessment(
            overall_risk=overall_risk,
            stability_risk="low",
            cost_risk="medium" if any(r.knob_type == KnobType.STRICTNESS for r in recommendations) else "low",
            quality_risk="low",
            risk_factors=risk_factors,
            mitigations=mitigations,
        )

    def _calculate_confidence(
        self,
        recommendations: List[TunerRecommendation]
    ) -> float:
        """計算處方信心度"""
        if not recommendations:
            return 0.5

        # 基礎信心度
        confidence = 0.7

        # 高優先級建議增加信心
        high_priority_count = sum(
            1 for r in recommendations if r.priority in ["high", "critical"]
        )
        confidence += high_priority_count * 0.05

        # 建議過多降低信心
        if len(recommendations) > 3:
            confidence -= (len(recommendations) - 3) * 0.05

        return max(0.4, min(0.95, confidence))

    async def _apply_action(
        self,
        action: GovernanceAction,
        workspace_id: str
    ) -> None:
        """套用單個動作"""
        # 這裡是佔位實現
        # 實際應該調用對應的設定服務
        logger.info(
            f"GovernanceTuner: Applying action {action.action_id} "
            f"({action.action_type.value} {action.target_knob.value} = {action.target_value}) "
            f"to workspace {workspace_id}"
        )

    def _generate_decision_summary(
        self,
        prescription: GovernancePrescription,
        applied: bool
    ) -> str:
        """生成決策摘要"""
        if not prescription.recommendations:
            return "無需調整"

        primary = prescription.primary_recommendation
        if applied:
            return f"已套用治理處方：{primary.knob_name} 調整為 {primary.suggested_value}"
        else:
            return f"治理處方套用失敗：{primary.knob_name} 調整"

    def _generate_rationale(
        self,
        prescription: GovernancePrescription
    ) -> str:
        """生成決策原因"""
        if not prescription.recommendations:
            return "目前執行穩定，無需調整"

        reasons = [r.rationale for r in prescription.recommendations[:2]]
        return "；".join(reasons)

