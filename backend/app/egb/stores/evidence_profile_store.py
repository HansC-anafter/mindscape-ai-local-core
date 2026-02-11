"""
Evidence Profile Store

Persistent storage interface: EGBRunIndex, EGBDriftReport, EGBIntentProfile

Design principles:
- Use SQLAlchemy ORM
- Provide async interface
- Support cache layer (optional)
"""

import logging
from typing import Optional, List, Dict, Any
from datetime import datetime, timezone


def _utc_now():
    """Return timezone-aware UTC now."""
    return datetime.now(timezone.utc)
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, desc

from backend.app.egb.models.egb_models import (
    EGBRunIndex,
    EGBDriftReport,
    EGBIntentProfile,
    ExternalJobMapping,  # P0-7: New addition
)
from backend.app.egb.schemas.correlation_ids import CorrelationIds
from backend.app.egb.schemas.drift_report import RunDriftReport, DriftScores
from backend.app.egb.schemas.evidence_profile import IntentEvidenceProfile

logger = logging.getLogger(__name__)


class EvidenceProfileStore:
    """
    Evidence profile store

    Provides persistent storage interface, supporting:
    - Run index queries
    - Drift report storage/queries
    - Intent profile aggregation/queries
    """

    def __init__(self, db_session: AsyncSession):
        """
        初始化 Store

        Args:
            db_session: SQLAlchemy async session
        """
        self.db = db_session

    # ===== EGBRunIndex 操作 =====

    async def save_run_index(
        self,
        correlation_ids: CorrelationIds,
        status: str = "pending",
        gate_passed: bool = False,
        error_count: int = 0,
        outcome: str = "pending",  # ⚠️ P0-10 新增：RunOutcome
    ) -> EGBRunIndex:
        """
        保存 Run 索引（存在則更新，不存在則創建）

        ⚠️ P0-B：存儲完整的 CorrelationIds（JSON）
        ⚠️ P0-10：支援 outcome 欄位
        ⚠️ 防重複寫入：如果 run_id 已存在，則更新現有記錄
        """
        # ⚠️ 先檢查是否存在
        existing = await self.get_run_index(correlation_ids.run_id)

        if existing:
            # Update if exists (preserve existing status/outcome unless explicitly provided)
            existing.correlation_ids_json = correlation_ids.to_dict()  # Update complete CorrelationIds
            existing.workspace_id = correlation_ids.workspace_id
            existing.intent_id = correlation_ids.intent_id
            existing.decision_id = correlation_ids.decision_id
            existing.playbook_id = correlation_ids.playbook_id
            existing.strictness_level = correlation_ids.strictness_level
            existing.mind_lens_level = correlation_ids.mind_lens_level
            existing.policy_version = correlation_ids.policy_version
            existing.playbook_version = correlation_ids.playbook_version
            existing.model_version = correlation_ids.model_version

            # Only update explicitly provided fields
            # If status/outcome is not "pending", update
            # If status/outcome is "pending" and existing value is also "pending", update (keep pending)
            # If status/outcome is "pending" but existing value is not "pending", preserve original value (don't overwrite)
            if status != "pending":
                existing.status = status
            elif existing.status == "pending":
                existing.status = status  # Keep pending
            # outcome 同理
            if outcome != "pending":
                existing.outcome = outcome
            elif existing.outcome == "pending":
                existing.outcome = outcome  # Keep pending
            existing.gate_passed = gate_passed
            existing.error_count = error_count

            existing.update_success()  # Recalculate is_success
            existing.updated_at = _utc_now()

            await self.db.commit()
            await self.db.refresh(existing)
            return existing
        else:
            # Create if doesn't exist
            run_index = EGBRunIndex(
                run_id=correlation_ids.run_id,
                workspace_id=correlation_ids.workspace_id,
                intent_id=correlation_ids.intent_id,
                decision_id=correlation_ids.decision_id,
                playbook_id=correlation_ids.playbook_id,
                correlation_ids_json=correlation_ids.to_dict(),  # ⚠️ P0-B：完整序列化
                strictness_level=correlation_ids.strictness_level,
                mind_lens_level=correlation_ids.mind_lens_level,
                policy_version=correlation_ids.policy_version,
                playbook_version=correlation_ids.playbook_version,
                model_version=correlation_ids.model_version,
                status=status,
                gate_passed=gate_passed,
                error_count=error_count,
                outcome=outcome,  # ⚠️ P0-10 新增
            )
            run_index.update_success()  # ⚠️ P0-2/P0-10：計算 is_success（考慮 outcome）

            self.db.add(run_index)
            await self.db.commit()
            await self.db.refresh(run_index)

            return run_index

    async def get_run_index(self, run_id: str) -> Optional[EGBRunIndex]:
        """獲取 Run 索引"""
        result = await self.db.execute(
            select(EGBRunIndex).where(EGBRunIndex.run_id == run_id)
        )
        return result.scalar_one_or_none()

    async def get_runs_by_intent(
        self,
        intent_id: str,
        policy_version: Optional[str] = None,
        limit: int = 100,
        only_success: bool = False,
    ) -> List[EGBRunIndex]:
        """
        獲取意圖的所有 runs

        ⚠️ P0-5：支持 policy_version 過濾
        ⚠️ P0-10：only_success 會過濾 outcome == "success" 的 runs（通過 is_success 欄位）
        """
        query = select(EGBRunIndex).where(
            EGBRunIndex.intent_id == intent_id
        )

        if policy_version:
            query = query.where(EGBRunIndex.policy_version == policy_version)

        if only_success:
            # ⚠️ P0-10：is_success 已經考慮了 outcome
            query = query.where(EGBRunIndex.is_success == True)

        query = query.order_by(desc(EGBRunIndex.created_at)).limit(limit)

        result = await self.db.execute(query)
        return list(result.scalars().all())

    async def update_run_status(
        self,
        run_id: str,
        status: Optional[str] = None,
        gate_passed: Optional[bool] = None,
        error_count: Optional[int] = None,
        outcome: Optional[str] = None,
    ) -> Optional[EGBRunIndex]:
        """
        更新 Run 狀態

        ⚠️ P0-10 擴展：支援 outcome 參數
        """
        run_index = await self.get_run_index(run_id)
        if not run_index:
            return None

        if status is not None:
            run_index.status = status
        if gate_passed is not None:
            run_index.gate_passed = gate_passed
        if error_count is not None:
            run_index.error_count = error_count
        if outcome is not None:
            run_index.outcome = outcome

        run_index.update_success()  # ⚠️ P0-2/P0-10：重新計算 is_success（考慮 outcome）
        run_index.updated_at = _utc_now()

        await self.db.commit()
        await self.db.refresh(run_index)

        return run_index

    # ===== EGBDriftReport 操作 =====

    async def save_drift_report(self, drift_report: RunDriftReport) -> EGBDriftReport:
        """保存漂移報告"""
        db_report = EGBDriftReport(
            report_id=drift_report.report_id,
            run_id=drift_report.run_id,
            baseline_run_id=drift_report.baseline_run_id,
            intent_id=drift_report.intent_id,
            workspace_id=drift_report.workspace_id,
            drift_scores_json=drift_report.drift_scores.to_dict(),
            overall_drift_score=drift_report.overall_drift_score,
            drift_level=drift_report.drift_level.value,
            semantic_diff_pointers=drift_report.semantic_diff_pointers,
            drift_explanations_json=[e.to_dict() for e in drift_report.drift_explanations],
            created_at=drift_report.created_at,
        )

        self.db.add(db_report)
        await self.db.commit()
        await self.db.refresh(db_report)

        return db_report

    async def get_drift_report(self, run_id: str) -> Optional[RunDriftReport]:
        """獲取漂移報告"""
        result = await self.db.execute(
            select(EGBDriftReport).where(EGBDriftReport.run_id == run_id)
            .order_by(desc(EGBDriftReport.created_at))
            .limit(1)
        )
        db_report = result.scalar_one_or_none()
        if not db_report:
            return None

        # Rebuild RunDriftReport
        return RunDriftReport.from_dict({
            "report_id": db_report.report_id,
            "run_id": db_report.run_id,
            "baseline_run_id": db_report.baseline_run_id,
            "intent_id": db_report.intent_id,
            "workspace_id": db_report.workspace_id,
            "drift_scores": db_report.drift_scores_json,
            "semantic_diff_pointers": db_report.semantic_diff_pointers or [],
            "drift_explanations": db_report.drift_explanations_json or [],
            "created_at": db_report.created_at.isoformat(),
        })

    # ===== EGBIntentProfile 操作 =====

    async def get_or_create_profile(
        self,
        intent_id: str,
        workspace_id: str,
        policy_version: Optional[str] = None,
    ) -> EGBIntentProfile:
        """獲取或創建意圖剖面"""
        profile_id = f"{intent_id}:{policy_version or 'default'}"

        result = await self.db.execute(
            select(EGBIntentProfile).where(EGBIntentProfile.profile_id == profile_id)
        )
        profile = result.scalar_one_or_none()

        if not profile:
            profile = EGBIntentProfile(
                profile_id=profile_id,
                intent_id=intent_id,
                workspace_id=workspace_id,
                policy_version=policy_version,
            )
            self.db.add(profile)
            await self.db.commit()
            await self.db.refresh(profile)

        return profile

    async def update_profile(
        self,
        profile: EGBIntentProfile,
        total_runs: Optional[int] = None,
        successful_runs: Optional[int] = None,
        failed_runs: Optional[int] = None,
        stability_score: Optional[float] = None,
        avg_drift_score: Optional[float] = None,
        total_tokens: Optional[int] = None,
        total_cost_usd: Optional[float] = None,
        avg_latency_ms: Optional[float] = None,
    ) -> EGBIntentProfile:
        """更新意圖剖面"""
        if total_runs is not None:
            profile.total_runs = total_runs
        if successful_runs is not None:
            profile.successful_runs = successful_runs
        if failed_runs is not None:
            profile.failed_runs = failed_runs
        if stability_score is not None:
            profile.stability_score = stability_score
        if avg_drift_score is not None:
            profile.avg_drift_score = avg_drift_score
        if total_tokens is not None:
            profile.total_tokens = total_tokens
        if total_cost_usd is not None:
            profile.total_cost_usd = total_cost_usd
        if avg_latency_ms is not None:
            profile.avg_latency_ms = avg_latency_ms

        profile.last_run_at = _utc_now()
        profile.updated_at = _utc_now()

        if profile.first_run_at is None:
            profile.first_run_at = _utc_now()

        await self.db.commit()
        await self.db.refresh(profile)

        return profile

    # ===== ExternalJobMapping 操作（P0-7）=====

    async def save_external_job_mapping(
        self,
        external_job_id: str,
        run_id: str,
        tool_name: str,
        external_run_id: Optional[str] = None,
        span_id: Optional[str] = None,
        status: str = "pending",
    ) -> ExternalJobMapping:
        """
        保存外部 job 映射

        ⚠️ P0-7 硬規則：用於將外部 callback 重新掛回同一個 run
        """
        mapping_id = f"{run_id}:{external_job_id}"

        mapping = ExternalJobMapping(
            mapping_id=mapping_id,
            external_job_id=external_job_id,
            external_run_id=external_run_id,
            tool_name=tool_name,
            run_id=run_id,
            span_id=span_id,
            status=status,
        )

        self.db.add(mapping)
        await self.db.commit()
        await self.db.refresh(mapping)

        return mapping

    async def get_external_job_mapping(
        self,
        external_job_id: str
    ) -> Optional[ExternalJobMapping]:
        """根據 external_job_id 獲取映射"""
        result = await self.db.execute(
            select(ExternalJobMapping).where(
                ExternalJobMapping.external_job_id == external_job_id
            )
        )
        return result.scalar_one_or_none()

    async def get_external_jobs_by_run(
        self,
        run_id: str
    ) -> List[ExternalJobMapping]:
        """獲取 run 的所有外部 job 映射"""
        result = await self.db.execute(
            select(ExternalJobMapping).where(
                ExternalJobMapping.run_id == run_id
            )
        )
        return list(result.scalars().all())

    async def update_external_job_status(
        self,
        external_job_id: str,
        status: str,
        callback_received_at: Optional[datetime] = None,
    ) -> Optional[ExternalJobMapping]:
        """更新外部 job 狀態（用於 callback）"""
        mapping = await self.get_external_job_mapping(external_job_id)
        if not mapping:
            return None

        mapping.status = status
        if callback_received_at:
            mapping.callback_received_at = callback_received_at
        mapping.updated_at = _utc_now()

        await self.db.commit()
        await self.db.refresh(mapping)

        return mapping

