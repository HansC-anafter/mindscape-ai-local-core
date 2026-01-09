"""
Run Outcome Schema

⚠️ P0-10：success/fail 定義落地到外部工具情境

擴展 P0-2 的 success/fail 定義，支援外部工具情境。
"""

from enum import Enum
from typing import Optional, Tuple
from dataclasses import dataclass

from backend.app.core.trace.trace_schema import TraceGraph, TraceStatus
from backend.app.egb.components.strictness_gate import GateResult


class RunOutcome(str, Enum):
    """
    Run 執行結果

    ⚠️ P0-10 硬規則：擴展 P0-2 的 success/fail，支援外部工具情境
    """
    SUCCESS = "success"  # 完全成功
    FAILED = "failed"  # 完全失敗
    PARTIAL = "partial"  # 部分成功（例如：內部成功但外部 job 失敗）
    PENDING_EXTERNAL = "pending_external"  # 等待外部 job 完成
    TIMEOUT = "timeout"  # 超時（內部或外部）


@dataclass
class RunOutcomeResult:
    """Run 執行結果"""
    outcome: RunOutcome
    gate_passed: Optional[bool] = None
    error_count: int = 0
    external_job_count: int = 0
    external_job_failed_count: int = 0
    external_job_pending_count: int = 0
    external_job_timeout_count: int = 0


def determine_run_outcome(
    trace_graph: TraceGraph,
    strictness_level: int,
    gate_result: Optional[GateResult] = None,
    error_count: int = 0,
    external_jobs: Optional[list] = None,  # List[ExternalJobNode]
) -> RunOutcomeResult:
    """
    決定 run 的執行結果（P0-10 擴展 P0-2）

    ⚠️ P0-10 硬規則：考慮外部 job 狀態

    規則：
    1. 基礎檢查（P0-2）：
       - trace.status == success AND
       - (strictness_level < 2 OR gate_L2_passed)
       - error_count = 0

    2. 外部 job 檢查（P0-10 新增）：
       - 如果有 external_jobs：
         - 所有 external_job.status == success → SUCCESS
         - 部分 external_job.status == failed → PARTIAL
         - 有 external_job.status == timeout → TIMEOUT
         - 有 external_job.status == pending → PENDING_EXTERNAL

    Args:
        trace_graph: Trace 圖
        strictness_level: 嚴謹度等級
        gate_result: Gate 檢查結果（可選）
        error_count: 錯誤數量
        external_jobs: 外部 job 列表（可選）

    Returns:
        RunOutcomeResult: 執行結果
    """
    external_jobs = external_jobs or []

    # 統計外部 job 狀態
    external_job_count = len(external_jobs)
    external_job_failed_count = 0
    external_job_pending_count = 0
    external_job_timeout_count = 0

    for job in external_jobs:
        if job.status == TraceStatus.FAILED:
            external_job_failed_count += 1
        elif job.status == TraceStatus.PENDING:
            external_job_pending_count += 1
        elif job.status == TraceStatus.CANCELLED:  # 超時視為 cancelled
            external_job_timeout_count += 1

    # 基礎檢查（P0-2）
    if trace_graph.has_error() or error_count > 0:
        return RunOutcomeResult(
            outcome=RunOutcome.FAILED,
            gate_passed=False,
            error_count=error_count,
            external_job_count=external_job_count,
            external_job_failed_count=external_job_failed_count,
            external_job_pending_count=external_job_pending_count,
            external_job_timeout_count=external_job_timeout_count,
        )

    gate_passed = None
    if strictness_level >= 2:
        # Level 2+ 必須通過 gate
        if not gate_result or not gate_result.passed:
            return RunOutcomeResult(
                outcome=RunOutcome.FAILED,
                gate_passed=False,
                error_count=error_count,
                external_job_count=external_job_count,
                external_job_failed_count=external_job_failed_count,
                external_job_pending_count=external_job_pending_count,
                external_job_timeout_count=external_job_timeout_count,
            )
        gate_passed = True

    # 外部 job 檢查（P0-10）
    if external_jobs:
        if external_job_pending_count > 0:
            return RunOutcomeResult(
                outcome=RunOutcome.PENDING_EXTERNAL,
                gate_passed=gate_passed,
                error_count=error_count,
                external_job_count=external_job_count,
                external_job_failed_count=external_job_failed_count,
                external_job_pending_count=external_job_pending_count,
                external_job_timeout_count=external_job_timeout_count,
            )

        if external_job_timeout_count > 0:
            return RunOutcomeResult(
                outcome=RunOutcome.TIMEOUT,
                gate_passed=gate_passed,
                error_count=error_count,
                external_job_count=external_job_count,
                external_job_failed_count=external_job_failed_count,
                external_job_pending_count=external_job_pending_count,
                external_job_timeout_count=external_job_timeout_count,
            )

        if external_job_failed_count > 0:
            # 部分失敗 → PARTIAL
            if external_job_failed_count < external_job_count:
                return RunOutcomeResult(
                    outcome=RunOutcome.PARTIAL,
                    gate_passed=gate_passed,
                    error_count=error_count,
                    external_job_count=external_job_count,
                    external_job_failed_count=external_job_failed_count,
                    external_job_pending_count=external_job_pending_count,
                    external_job_timeout_count=external_job_timeout_count,
                )
            # 全部失敗 → FAILED
            return RunOutcomeResult(
                outcome=RunOutcome.FAILED,
                gate_passed=gate_passed,
                error_count=error_count,
                external_job_count=external_job_count,
                external_job_failed_count=external_job_failed_count,
                external_job_pending_count=external_job_pending_count,
                external_job_timeout_count=external_job_timeout_count,
            )

    # 完全成功
    return RunOutcomeResult(
        outcome=RunOutcome.SUCCESS,
        gate_passed=gate_passed,
        error_count=error_count,
        external_job_count=external_job_count,
        external_job_failed_count=external_job_failed_count,
        external_job_pending_count=external_job_pending_count,
        external_job_timeout_count=external_job_timeout_count,
    )

