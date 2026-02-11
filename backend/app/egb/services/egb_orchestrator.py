"""
EGB Orchestrator

EGB 流程編排器，整合所有元件的執行流程。
"""

import logging
from typing import Optional, List, Dict, Any
from dataclasses import dataclass
from datetime import datetime, timezone


def _utc_now():
    """Return timezone-aware UTC now."""
    return datetime.now(timezone.utc)

from backend.app.egb.schemas.correlation_ids import CorrelationIds
from backend.app.egb.schemas.evidence_profile import IntentEvidenceProfile
from backend.app.egb.schemas.drift_report import RunDriftReport
from backend.app.egb.schemas.governance_prescription import GovernancePrescription
from backend.app.egb.schemas.structured_evidence import StructuredEvidence
from backend.app.egb.schemas.run_outcome import RunOutcome, determine_run_outcome  # ⚠️ P0-10 新增

from backend.app.egb.components.trace_linker import TraceLinker
from backend.app.egb.components.evidence_reducer import EvidenceReducer
from backend.app.egb.components.drift_scorer import DriftScorer
from backend.app.egb.components.policy_attributor import PolicyAttributor
from backend.app.egb.components.lens_explainer import LensExplainer
from backend.app.egb.components.governance_tuner import GovernanceTuner, GovernanceSettings

from backend.app.core.trace.trace_schema import TraceGraph

logger = logging.getLogger(__name__)


@dataclass
class EGBProcessResult:
    """EGB 處理結果"""
    correlation_ids: CorrelationIds
    structured_evidence: Optional[StructuredEvidence] = None
    drift_report: Optional[RunDriftReport] = None
    prescription: Optional[GovernancePrescription] = None
    errors: List[str] = None

    def __post_init__(self):
        if self.errors is None:
            self.errors = []


class EGBOrchestrator:
    """
    EGB 流程編排器

    整合 6 個核心元件的執行流程：
    TraceLinker → EvidenceReducer → DriftScorer → PolicyAttributor →
    (LensExplainer) → GovernanceTuner → DecisionRecord

    ⚠️ 計畫接口：
    - register_run(correlation_ids)：註冊 run（建立索引）
    - get_drift_report(run_id, baseline_run_id=None)：獲取漂移報告

    使用方式：
        orchestrator = EGBOrchestrator()
        await orchestrator.register_run(correlation_ids)
        drift_report = await orchestrator.get_drift_report(run_id)
    """

    def __init__(
        self,
        trace_linker: Optional[TraceLinker] = None,
        evidence_reducer: Optional[EvidenceReducer] = None,
        drift_scorer: Optional[DriftScorer] = None,
        policy_attributor: Optional[PolicyAttributor] = None,
        lens_explainer: Optional[LensExplainer] = None,
        governance_tuner: Optional[GovernanceTuner] = None,
        langfuse_adapter=None,  # ⚠️ 新增：LangfuseAdapter
        store=None,  # ⚠️ 新增：持久化存儲（TODO）
    ):
        """
        初始化 EGB 編排器

        所有元件都可選，未提供時會創建預設實例。
        """
        # ⚠️ 優先使用傳入的 store，確保 TraceLinker 接入持久化
        self.store = store
        self.trace_linker = trace_linker or TraceLinker(store=store)  # ⚠️ 傳入 store
        self.evidence_reducer = evidence_reducer or EvidenceReducer()
        self.drift_scorer = drift_scorer or DriftScorer()
        self.policy_attributor = policy_attributor or PolicyAttributor()
        self.lens_explainer = lens_explainer or LensExplainer()
        self.governance_tuner = governance_tuner or GovernanceTuner()
        self.langfuse_adapter = langfuse_adapter

        # In-memory storage (as cache, but prefer querying from store)
        self._evidence_cache: Dict[str, StructuredEvidence] = {}
        self._profile_cache: Dict[str, IntentEvidenceProfile] = {}

    async def register_run(self, correlation_ids: CorrelationIds) -> None:
        """
        Register run (create index)

        Planned interface: register_run only creates index
        Ensure write to store so queries work after restart
        """
        # Prioritize writing to store (if available)
        # save_run_index already supports "update if exists", won't duplicate writes
        if self.store:
            try:
                await self.store.save_run_index(
                    correlation_ids=correlation_ids,
                    status="pending",
                )
                logger.debug(f"EGBOrchestrator: Saved/updated run {correlation_ids.run_id} to store")
            except Exception as e:
                logger.warning(f"EGBOrchestrator: Failed to save run index: {e}")
                # Don't raise exception, allow execution to continue (may already exist)

        link_result = await self.trace_linker.register_run(correlation_ids)
        if not link_result.success:
            logger.error(f"EGBOrchestrator: Failed to register run: {link_result.error}")
            raise RuntimeError(f"Failed to register run: {link_result.error}")

    async def process_run(
        self,
        correlation_ids: CorrelationIds,
        trace_graph: TraceGraph,
        current_settings: Optional[GovernanceSettings] = None,
    ) -> EGBProcessResult:
        """
        Process single execution

        Complete EGB flow:
        1. Link trace
        2. Converge evidence
        3. Calculate drift
        4. Attribute drift
        5. Generate governance prescription

        Args:
            correlation_ids: 關聯 ID
            trace_graph: Trace 圖
            current_settings: 當前治理設定

        Returns:
            EGBProcessResult: 處理結果
        """
        result = EGBProcessResult(correlation_ids=correlation_ids)

        try:
            # Step 1: 註冊 run（建立索引）
            # ⚠️ 確保寫入 store，以便重啟後仍能查詢
            # ⚠️ save_run_index 已支持「存在則更新」，不會重複寫入
            if self.store:
                try:
                    await self.store.save_run_index(
                        correlation_ids=correlation_ids,
                        status="pending",
                    )
                    logger.debug(f"EGBOrchestrator: Saved/updated run {correlation_ids.run_id} to store in process_run")
                except Exception as e:
                    logger.warning(f"EGBOrchestrator: Failed to save run index in process_run: {e}")
                    # Don't raise exception, allow execution to continue

            # ⚠️ P0-3：TraceLinker 只負責索引查詢，不負責 propagation
            link_result = await self.trace_linker.register_run(correlation_ids)
            if not link_result.success:
                result.errors.append(f"TraceLinker failed: {link_result.error}")

            # ⚠️ P0-10：提取 external_jobs 用於 outcome 計算
            external_jobs = [
                node for node in trace_graph.nodes
                if hasattr(node, 'node_type') and node.node_type.value == "external_job"
            ]

            # Step 2: 收斂證據
            # ⚠️ P0-1：使用新的接口 reduce_trace(trace, correlation_ids)
            evidence = await self.evidence_reducer.reduce_trace(
                trace=trace_graph,
                correlation_ids=correlation_ids,
            )
            result.structured_evidence = evidence
            self._evidence_cache[correlation_ids.run_id] = evidence

            # Step 3: 獲取基準並計算漂移
            # ⚠️ P0-5：使用 BaselinePicker（支援 policy_version 限制）
            from backend.app.egb.services.baseline_picker import BaselinePicker, BaselineStrategy

            baseline_picker = BaselinePicker(
                trace_linker=self.trace_linker,
                evidence_cache=self._evidence_cache,
                orchestrator=self,  # ⚠️ 傳入 orchestrator 以便重建證據
            )

            baseline_selection = await baseline_picker.pick_baseline(
                intent_id=correlation_ids.intent_id,
                current_policy_version=correlation_ids.policy_version or "default",
                strategy=BaselineStrategy.LAST_SUCCESS,
                allow_cross_version=False,  # MVP 預設不允許跨版本
                current_run_id=correlation_ids.run_id,
            )

            if baseline_selection.has_baseline:
                baseline_run_id = baseline_selection.baseline_run_id
                baseline_evidence = self._evidence_cache.get(baseline_run_id)

                # ⚠️ 如果 cache 沒有，從 Langfuse 重建證據
                if not baseline_evidence:
                    baseline_correlation_ids = await self.trace_linker.get_run_by_id(baseline_run_id)
                    if baseline_correlation_ids:
                        baseline_evidence = await self._rebuild_evidence(baseline_run_id, baseline_correlation_ids)
                        if baseline_evidence:
                            self._evidence_cache[baseline_run_id] = baseline_evidence
                            logger.info(f"EGBOrchestrator: Rebuilt baseline evidence for {baseline_run_id}")

                if baseline_evidence:
                    # Step 3a: 計算漂移分數
                    drift_scores = await self.drift_scorer.compute_drift(
                        current=evidence,
                        baseline=baseline_evidence,
                        store=self.store,  # ⚠️ 傳入 store 以便 external_job_drift 查詢狀態
                    )

                    # Step 4: 歸因漂移
                    attributions = await self.policy_attributor.attribute_drift(
                        drift_scores=drift_scores,
                        current_evidence=evidence,
                        baseline_evidence=baseline_evidence,
                    )

                    # Create drift report
                    # ⚠️ P0-5：新增 semantic_diff_pointers
                    semantic_diff_pointers = []
                    if evidence.key_fields_hash_map and baseline_evidence.key_fields_hash_map:
                        current_keys = set(evidence.key_fields_hash_map.keys())
                        baseline_keys = set(baseline_evidence.key_fields_hash_map.keys())
                        all_keys = current_keys | baseline_keys
                        for key in all_keys:
                            if evidence.key_fields_hash_map.get(key) != baseline_evidence.key_fields_hash_map.get(key):
                                semantic_diff_pointers.append(key)

                    result.drift_report = RunDriftReport(
                        run_id=correlation_ids.run_id,
                        baseline_run_id=baseline_run_id,
                        intent_id=correlation_ids.intent_id,
                        workspace_id=correlation_ids.workspace_id,
                        drift_scores=drift_scores,
                        drift_explanations=attributions,
                        semantic_diff_pointers=semantic_diff_pointers,  # ⚠️ P0-5 新增
                    )

                    # Step 5: 生成治理處方
                    settings = current_settings or GovernanceSettings()
                    result.prescription = await self.governance_tuner.generate_prescription(
                        drift_report=result.drift_report,
                        attribution=attributions,
                        current_settings=settings,
                    )

            # Update Intent Evidence Profile
            await self._update_evidence_profile(correlation_ids, evidence)

            logger.info(
                f"EGBOrchestrator: Processed run {correlation_ids.run_id} "
                f"for intent {correlation_ids.intent_id}"
            )

        except Exception as e:
            logger.error(f"EGBOrchestrator: Failed to process run: {e}")
            result.errors.append(str(e))

        return result

    async def get_intent_profile(
        self,
        intent_id: str,
        workspace_id: str,
    ) -> Optional[IntentEvidenceProfile]:
        """
        獲取意圖證據剖面

        Args:
            intent_id: 意圖 ID
            workspace_id: 工作空間 ID

        Returns:
            IntentEvidenceProfile 或 None
        """
        cache_key = f"{workspace_id}:{intent_id}"
        profile = self._profile_cache.get(cache_key)

        if not profile:
            # Create new profile
            profile = IntentEvidenceProfile(
                intent_id=intent_id,
                workspace_id=workspace_id,
            )
            self._profile_cache[cache_key] = profile

        return profile

    async def get_drift_report(
        self,
        run_id: str,
        baseline_run_id: Optional[str] = None,
    ) -> Optional[RunDriftReport]:
        """
        獲取執行漂移報告

        ⚠️ 計畫接口：完整的 drift report 流程
        1. 從 run_index 獲取 correlation_ids
        2. adapter 拉 raw trace
        3. normalizer → graph
        4. reducer → evidence（可 cache）
        5. baseline picker（如果沒有指定 baseline_run_id）
        6. reducer baseline evidence（可 cache）
        7. drift scorer
        8. 存 store + 回傳

        Args:
            run_id: 執行 ID
            baseline_run_id: 基準執行 ID（可選，不提供則使用 BaselinePicker）

        Returns:
            RunDriftReport 或 None
        """
        # 1. 取得 correlation_ids（從 run_index，優先從 store）
        correlation_ids = await self.trace_linker.get_run_by_id(run_id)
        if not correlation_ids:
            logger.warning(f"EGBOrchestrator: Run {run_id} not found")
            return None

        # 2. 獲取當前證據（從 cache 或重新計算）
        current_evidence = self._evidence_cache.get(run_id)
        if not current_evidence:
            # ⚠️ 從 Langfuse 獲取 trace 並重新計算證據
            current_evidence = await self._rebuild_evidence(run_id, correlation_ids)
            if not current_evidence:
                logger.warning(f"EGBOrchestrator: Failed to rebuild evidence for run {run_id}")
                return None
            # Store in cache
            self._evidence_cache[run_id] = current_evidence

        # 3. 確定基準
        if baseline_run_id:
            baseline_evidence = self._evidence_cache.get(baseline_run_id)
            if not baseline_evidence:
                # ⚠️ 從 Langfuse 獲取 trace 並重新計算基準證據
                baseline_correlation_ids = await self.trace_linker.get_run_by_id(baseline_run_id)
                if baseline_correlation_ids:
                    baseline_evidence = await self._rebuild_evidence(baseline_run_id, baseline_correlation_ids)
                    if baseline_evidence:
                        self._evidence_cache[baseline_run_id] = baseline_evidence
                if not baseline_evidence:
                    logger.warning(f"EGBOrchestrator: Baseline evidence for {baseline_run_id} not found")
                    return None
        else:
            # Use BaselinePicker to select baseline
            from backend.app.egb.services.baseline_picker import BaselinePicker, BaselineStrategy

            baseline_picker = BaselinePicker(
                trace_linker=self.trace_linker,
                evidence_cache=self._evidence_cache,
                orchestrator=self,  # ⚠️ 傳入 orchestrator 以便重建證據
            )

            baseline_selection = await baseline_picker.pick_baseline(
                intent_id=correlation_ids.intent_id,
                current_policy_version=correlation_ids.policy_version or "default",
                strategy=BaselineStrategy.LAST_SUCCESS,
                allow_cross_version=False,
                current_run_id=run_id,
            )

            if not baseline_selection.has_baseline:
                logger.info(f"EGBOrchestrator: No baseline found for run {run_id}")
                return None

            baseline_run_id = baseline_selection.baseline_run_id
            baseline_evidence = self._evidence_cache.get(baseline_run_id)

            if not baseline_evidence:
                # ⚠️ 從 Langfuse 獲取 trace 並重新計算基準證據
                baseline_correlation_ids = await self.trace_linker.get_run_by_id(baseline_run_id)
                if baseline_correlation_ids:
                    baseline_evidence = await self._rebuild_evidence(baseline_run_id, baseline_correlation_ids)
                    if baseline_evidence:
                        self._evidence_cache[baseline_run_id] = baseline_evidence
                if not baseline_evidence:
                    logger.warning(f"EGBOrchestrator: Baseline evidence for {baseline_run_id} not found")
                    return None

        # 4. 計算漂移
        drift_scores = await self.drift_scorer.compute_drift(
            current=current_evidence,
            baseline=baseline_evidence,
            store=self.store,  # ⚠️ 傳入 store 以便 external_job_drift 查詢狀態
        )

        # 5. 歸因漂移
        attributions = await self.policy_attributor.attribute_drift(
            drift_scores=drift_scores,
            current_evidence=current_evidence,
            baseline_evidence=baseline_evidence,
        )

        # 6. 計算 semantic_diff_pointers
        semantic_diff_pointers = []
        if current_evidence.key_fields_hash_map and baseline_evidence.key_fields_hash_map:
            current_keys = set(current_evidence.key_fields_hash_map.keys())
            baseline_keys = set(baseline_evidence.key_fields_hash_map.keys())
            all_keys = current_keys | baseline_keys
            for key in all_keys:
                if current_evidence.key_fields_hash_map.get(key) != baseline_evidence.key_fields_hash_map.get(key):
                    semantic_diff_pointers.append(key)

        # 7. 創建漂移報告
        drift_report = RunDriftReport(
            run_id=run_id,
            baseline_run_id=baseline_run_id,
            intent_id=correlation_ids.intent_id,
            workspace_id=correlation_ids.workspace_id,
            drift_scores=drift_scores,
            drift_explanations=attributions,
            semantic_diff_pointers=semantic_diff_pointers,  # ⚠️ P0-5 新增
        )

        # 8. 存 store（如果可用）
        if self.store:
            await self.store.save_drift_report(drift_report)

        return drift_report

    async def _rebuild_evidence(
        self,
        run_id: str,
        correlation_ids: CorrelationIds
    ) -> Optional[StructuredEvidence]:
        """
        從 Langfuse 重建證據

        ⚠️ 完整流程（含降級策略）：
        1. 優先：從 Langfuse 獲取 trace → Normalizer → Reducer
        2. 降級：如果 Langfuse 不可用，嘗試從 store 讀取已保存的 evidence（如果之前保存過）

        Args:
            run_id: Run ID
            correlation_ids: CorrelationIds

        Returns:
            StructuredEvidence 或 None
        """
        # ⚠️ 降級策略 1：如果 Langfuse 不可用，嘗試從 store 讀取已保存的 evidence
        if not self.langfuse_adapter or not self.langfuse_adapter._client:
            logger.warning("EGBOrchestrator: No langfuse_adapter, trying to load evidence from store")
            if self.store:
                # TODO: 如果 store 支持保存/讀取 StructuredEvidence，可以從這裡讀取
                # Store currently has no interface to save evidence, needs extension
                logger.warning("EGBOrchestrator: Store does not support loading evidence yet")
            return None

        try:
            # 1. 從 Langfuse 獲取 trace
            langfuse_trace = await self.langfuse_adapter.get_trace(run_id)
            if not langfuse_trace:
                logger.warning(f"EGBOrchestrator: Trace {run_id} not found in Langfuse")
                # ⚠️ 降級策略 2：如果 trace 不存在，嘗試從 store 讀取
                if self.store:
                    # TODO: 從 store 讀取已保存的 evidence
                    logger.warning("EGBOrchestrator: Store does not support loading evidence yet")
                return None

            # 2. Normalizer → TraceGraph
            from backend.app.egb.integrations.trace_normalizer import TraceNormalizer
            normalizer = TraceNormalizer()
            normalization_result = normalizer.normalize(langfuse_trace, run_id=run_id)

            if not normalization_result.success:
                logger.warning(f"EGBOrchestrator: Failed to normalize trace {run_id}: {normalization_result.error}")
                # ⚠️ 降級策略 3：如果 normalization 失敗，嘗試從 store 讀取
                if self.store:
                    # TODO: 從 store 讀取已保存的 evidence
                    logger.warning("EGBOrchestrator: Store does not support loading evidence yet")
                return None

            trace_graph = normalization_result.trace_graph

            # 3. Reducer → StructuredEvidence
            evidence = await self.evidence_reducer.reduce_trace(
                trace=trace_graph,
                correlation_ids=correlation_ids,
            )

            logger.info(f"EGBOrchestrator: Rebuilt evidence for run {run_id}")
            return evidence

        except Exception as e:
            logger.error(f"EGBOrchestrator: Failed to rebuild evidence for run {run_id}: {e}")
            # ⚠️ 降級策略 4：如果重建失敗，嘗試從 store 讀取
            if self.store:
                # TODO: 從 store 讀取已保存的 evidence
                logger.warning("EGBOrchestrator: Store does not support loading evidence yet")
            return None

    async def explain_drift(
        self,
        run_id: str,
        user_context: Optional[str] = None,
    ) -> Optional[str]:
        """
        請求 LLM 解釋漂移

        這是觸發 LensExplainer 的入口點。

        Args:
            run_id: 執行 ID
            user_context: 用戶上下文

        Returns:
            解釋文字或 None
        """
        # Get drift report
        drift_report = await self.get_drift_report(run_id)
        if not drift_report:
            return None

        # Call LensExplainer
        result = await self.lens_explainer.explain_drift(
            drift_report=drift_report,
            attribution=drift_report.drift_explanations,
            user_context=user_context,
        )

        # Update drift report
        drift_report.llm_explanation = result.explanation
        drift_report.needs_llm_explanation = False

        return result.explanation

    async def _update_evidence_profile(
        self,
        correlation_ids: CorrelationIds,
        evidence: StructuredEvidence,
    ) -> None:
        """
        更新意圖證據剖面

        ⚠️ 優先從 store 讀取 run_index/outcome，確保與 callback 更新同步
        """
        cache_key = f"{correlation_ids.workspace_id}:{correlation_ids.intent_id}"

        profile = self._profile_cache.get(cache_key)
        if not profile:
            profile = IntentEvidenceProfile(
                intent_id=correlation_ids.intent_id,
                workspace_id=correlation_ids.workspace_id,
            )
            self._profile_cache[cache_key] = profile

        # ⚠️ 優先從 store 讀取 run_index/outcome（如果可用）
        is_success = False
        if self.store:
            run_index = await self.store.get_run_index(correlation_ids.run_id)
            if run_index:
                # Use store's is_success (outcome already considered)
                is_success = run_index.is_success
            else:
                # Fallback：使用 evidence 的 error_count
                is_success = evidence.metrics.error_count == 0
        else:
            # Fallback：使用 evidence 的 error_count
            is_success = evidence.metrics.error_count == 0

        # Update statistics
        profile.total_runs += 1
        if is_success:
            profile.successful_runs += 1
        else:
            profile.failed_runs += 1

        # Update time range
        now = _utc_now()
        if profile.first_run_at is None:
            profile.first_run_at = now
        profile.last_run_at = now

        # Update cost statistics
        profile.total_tokens += evidence.metrics.total_tokens
        profile.total_cost_usd += evidence.metrics.total_cost_usd

        # Update average latency
        if profile.total_runs > 0:
            profile.avg_latency_ms = (
                (profile.avg_latency_ms * (profile.total_runs - 1) +
                 evidence.metrics.total_latency_ms) / profile.total_runs
            )

        # Update stability (P0-10: Consider RunOutcome)
        # Extract external_jobs from trace_graph
        from backend.app.core.trace.trace_schema import TraceNodeType
        external_jobs = [
            node for node in trace_graph.nodes
            if hasattr(node, 'node_type') and node.node_type == TraceNodeType.EXTERNAL_JOB
        ]

        # Get gate_result (if available)
        gate_result = None  # TODO: 從 StrictnessGate 獲取

        outcome_result = determine_run_outcome(
            trace_graph=trace_graph,
            strictness_level=correlation_ids.strictness_level,
            gate_result=gate_result,
            error_count=evidence.metrics.error_count,
            external_jobs=external_jobs,
        )

        # ⚠️ P0-10：保存 outcome 到 store
        if self.store:
            await self.store.update_run_status(
                run_id=correlation_ids.run_id,
                outcome=outcome_result.outcome.value,
                gate_passed=outcome_result.gate_passed,
                error_count=outcome_result.error_count,
            )

            # Update stability (consider outcome)
        drift_score = 0.0  # TODO: 從 drift_report 獲取
        if outcome_result.outcome == RunOutcome.SUCCESS:
            # Normal calculation
            profile.update_stability_score()
        elif outcome_result.outcome == RunOutcome.PARTIAL:
            # Partial success, stability discounted
            profile.stability_score = profile.stability_score * 0.7
        else:
            # Failed/timeout, stability decreases
            profile.stability_score = max(0.0, profile.stability_score - 0.1)

        profile.updated_at = now

