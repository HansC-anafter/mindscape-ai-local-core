"""
Governance tuner.

Produces executable governance recommendations such as strictness upgrades,
toolset narrowing, and scope locking, then records decisions.
"""

import logging
from datetime import timedelta
from typing import List, Optional
import uuid

from backend.app.egb.components.governance_tuner_support import (
    ApplyResult,
    GovernanceSettings,
    _utc_now,
)
from backend.app.egb.schemas.decision_record import (
    DecisionRecord,
    DecisionSource,
    DecisionType,
)
from backend.app.egb.schemas.drift_report import (
    DriftExplanation,
    DriftLevel,
    DriftType,
    RunDriftReport,
)
from backend.app.egb.schemas.governance_prescription import (
    ActionType,
    ExpectedOutcome,
    GovernanceAction,
    GovernancePrescription,
    KnobType,
    RiskAssessment,
    TunerRecommendation,
)

logger = logging.getLogger(__name__)


class GovernanceTuner:
    """
    Generate governance prescriptions and record decisions.

    Responsibilities:
    1. Generate prescriptions from drift reports.
    2. Provide one-step apply behavior.
    3. Record all decisions as DecisionRecord entries.
    """

    STRICTNESS_UPGRADE_THRESHOLD = {
        DriftLevel.MILD: 0,
        DriftLevel.MODERATE: 1,
        DriftLevel.HIGH: 2,
    }

    def __init__(self, settings_store=None):
        """
        Initialize the governance tuner.

        Args:
            settings_store: Optional governance settings store.
        """
        self.settings_store = settings_store

    async def generate_prescription(
        self,
        drift_report: RunDriftReport,
        attribution: List[DriftExplanation],
        current_settings: GovernanceSettings,
    ) -> GovernancePrescription:
        """
        Generate a governance prescription from drift evidence.

        Args:
            drift_report: Drift report to evaluate.
            attribution: Drift attribution explanations.
            current_settings: Current governance settings.

        Returns:
            Governance prescription.
        """
        prescription = GovernancePrescription(
            prescription_id=str(uuid.uuid4()),
            intent_id=drift_report.intent_id,
            run_id=drift_report.run_id,
            workspace_id=drift_report.workspace_id,
            created_at=_utc_now(),
            expires_at=_utc_now() + timedelta(hours=24),
        )

        recommendations = []
        actions = []

        if drift_report.drift_level in [DriftLevel.MODERATE, DriftLevel.HIGH]:
            strictness_rec = self._generate_strictness_recommendation(
                drift_report,
                current_settings,
            )
            if strictness_rec:
                recommendations.append(strictness_rec)
                actions.extend(
                    self._create_strictness_actions(strictness_rec, current_settings)
                )

        for explanation in attribution:
            rec = self._generate_recommendation_for_drift(
                explanation,
                current_settings,
            )
            if rec:
                recommendations.append(rec)

        prescription.recommendations = recommendations
        prescription.applicable_actions = actions
        prescription.expected_outcomes = self._generate_expected_outcomes(
            recommendations,
            drift_report,
        )
        prescription.risk_assessment = self._assess_risk(
            recommendations,
            drift_report,
        )
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
        user_id: str = "system",
    ) -> ApplyResult:
        """
        Apply a governance prescription.

        Args:
            prescription: Governance prescription to apply.
            workspace_id: Workspace identifier.
            user_id: Actor identifier.

        Returns:
            Apply result.
        """
        applied_actions = []
        failed_actions = []

        for action in prescription.applicable_actions:
            try:
                await self._apply_action(action, workspace_id)
                applied_actions.append(action.action_id)
            except Exception as exc:
                logger.error(f"Failed to apply action {action.action_id}: {exc}")
                failed_actions.append(action.action_id)

        success = len(failed_actions) == 0
        decision_record = await self.record_decision(
            prescription=prescription,
            applied=success,
            user_id=user_id,
            applied_actions=applied_actions,
            failed_actions=failed_actions,
        )

        prescription.status = "applied" if success else "partially_applied"
        prescription.applied_at = _utc_now()
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
        Record a governance decision.

        Args:
            prescription: Governance prescription.
            applied: Whether the prescription was applied.
            user_id: Decision actor identifier.
            applied_actions: Applied action identifiers.
            failed_actions: Failed action identifiers.

        Returns:
            Decision record.
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
            decided_at=_utc_now(),
            status="executed" if applied else "failed",
        )

        record.add_evidence(
            evidence_type="prescription",
            evidence_id=prescription.prescription_id,
            description="治理處方",
        )

        logger.info(
            f"GovernanceTuner: Recorded decision {record.record_id} "
            f"for prescription {prescription.prescription_id}"
        )

        return record

    def _generate_strictness_recommendation(
        self,
        drift_report: RunDriftReport,
        current_settings: GovernanceSettings,
    ) -> Optional[TunerRecommendation]:
        """Generate a strictness adjustment recommendation."""
        upgrade_amount = self.STRICTNESS_UPGRADE_THRESHOLD.get(
            drift_report.drift_level,
            0,
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
            risk_if_ignored=(
                "high" if drift_report.drift_level == DriftLevel.HIGH else "medium"
            ),
        )

    def _generate_recommendation_for_drift(
        self,
        explanation: DriftExplanation,
        current_settings: GovernanceSettings,
    ) -> Optional[TunerRecommendation]:
        """Generate a recommendation for a specific drift type."""
        if explanation.drift_type == DriftType.EVIDENCE:
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
        current_settings: GovernanceSettings,
    ) -> List[GovernanceAction]:
        """Create actions for strictness adjustment."""
        actions = []
        new_level = recommendation.suggested_value

        actions.append(
            GovernanceAction(
                action_type=ActionType.SET,
                target_knob=KnobType.STRICTNESS,
                target_value=new_level,
                label=f"提高嚴謹度到 Level {new_level}",
                description=f"將嚴謹度從 {current_settings.strictness_level} 調整到 {new_level}",
                requires_confirmation=new_level >= 2,
                confirmation_message=(
                    f"確定要將嚴謹度提高到 Level {new_level}？這可能會增加執行時間和成本。"
                    if new_level >= 2
                    else None
                ),
            )
        )

        return actions

    def _generate_expected_outcomes(
        self,
        recommendations: List[TunerRecommendation],
        drift_report: RunDriftReport,
    ) -> List[ExpectedOutcome]:
        """Generate expected outcomes for the prescription."""
        outcomes = []

        if recommendations:
            outcomes.append(
                ExpectedOutcome(
                    outcome_type="stability",
                    direction="improve",
                    magnitude="moderate" if len(recommendations) > 1 else "slight",
                    description="執行結果的一致性將提高",
                )
            )

        strictness_recs = [
            rec for rec in recommendations if rec.knob_type == KnobType.STRICTNESS
        ]
        if strictness_recs:
            outcomes.append(
                ExpectedOutcome(
                    outcome_type="cost",
                    direction=(
                        "increase"
                        if strictness_recs[0].suggested_value
                        > strictness_recs[0].current_value
                        else "neutral"
                    ),
                    magnitude="slight",
                    description="可能略微增加執行成本和時間",
                )
            )

        return outcomes

    def _assess_risk(
        self,
        recommendations: List[TunerRecommendation],
        drift_report: RunDriftReport,
    ) -> RiskAssessment:
        """Assess risks introduced by recommendations."""
        risk_factors = []
        mitigations = []

        for rec in recommendations:
            if rec.risk_if_applied == "high":
                risk_factors.append(f"{rec.knob_name} 調整可能帶來副作用")
                mitigations.append(f"建議先在測試環境驗證 {rec.knob_name} 的調整")

        high_risk_count = sum(
            1 for rec in recommendations if rec.risk_if_applied == "high"
        )

        if high_risk_count >= 2:
            overall_risk = "high"
        elif high_risk_count == 1 or len(recommendations) >= 3:
            overall_risk = "medium"
        else:
            overall_risk = "low"

        return RiskAssessment(
            overall_risk=overall_risk,
            stability_risk="low",
            cost_risk=(
                "medium"
                if any(rec.knob_type == KnobType.STRICTNESS for rec in recommendations)
                else "low"
            ),
            quality_risk="low",
            risk_factors=risk_factors,
            mitigations=mitigations,
        )

    def _calculate_confidence(
        self,
        recommendations: List[TunerRecommendation],
    ) -> float:
        """Calculate prescription confidence."""
        if not recommendations:
            return 0.5

        confidence = 0.7
        high_priority_count = sum(
            1 for rec in recommendations if rec.priority in ["high", "critical"]
        )
        confidence += high_priority_count * 0.05

        if len(recommendations) > 3:
            confidence -= (len(recommendations) - 3) * 0.05

        return max(0.4, min(0.95, confidence))

    async def _apply_action(
        self,
        action: GovernanceAction,
        workspace_id: str,
    ) -> None:
        """Apply a single governance action."""
        logger.info(
            f"GovernanceTuner: Applying action {action.action_id} "
            f"({action.action_type.value} {action.target_knob.value} = {action.target_value}) "
            f"to workspace {workspace_id}"
        )

    def _generate_decision_summary(
        self,
        prescription: GovernancePrescription,
        applied: bool,
    ) -> str:
        """Generate the decision summary."""
        if not prescription.recommendations:
            return "無需調整"

        primary = prescription.primary_recommendation
        if applied:
            return f"已套用治理處方：{primary.knob_name} 調整為 {primary.suggested_value}"
        return f"治理處方套用失敗：{primary.knob_name} 調整"

    def _generate_rationale(
        self,
        prescription: GovernancePrescription,
    ) -> str:
        """Generate the decision rationale."""
        if not prescription.recommendations:
            return "目前執行穩定，無需調整"

        reasons = [rec.rationale for rec in prescription.recommendations[:2]]
        return "；".join(reasons)
