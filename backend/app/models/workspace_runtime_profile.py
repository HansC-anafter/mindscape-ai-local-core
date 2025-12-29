"""
Workspace Runtime Profile Model

Defines execution contracts and operational postures for workspaces.
This is a lower-level configuration layer orthogonal to Mind-Lens and IntentCard.
"""

from datetime import datetime
from typing import Optional, Dict, Any, List, Literal, TYPE_CHECKING
from enum import Enum
from pydantic import BaseModel, Field

from .workspace import ExecutionMode

if TYPE_CHECKING:
    from .workspace import Workspace


# ==================== Enums ====================

class RationaleLevel(str, Enum):
    """Output rationale level"""
    NONE = "none"
    BRIEF = "brief"
    DETAILED = "detailed"


class CodingStyle(str, Enum):
    """Coding output style"""
    PATCH_FIRST = "patch_first"
    EXPLAIN_FIRST = "explain_first"
    CODE_ONLY = "code_only"


class WritingStyle(str, Enum):
    """Writing output style"""
    STRUCTURE_FIRST = "structure_first"
    DRAFT_FIRST = "draft_first"
    BOTH = "both"


class ConfirmationFormat(str, Enum):
    """Confirmation format"""
    LIST_CHANGES = "list_changes"
    SUMMARY = "summary"
    DETAILED = "detailed"


# ==================== Sub-models ====================

class InteractionBudget(BaseModel):
    """Interaction Budget - 交互預算"""

    max_questions_per_turn: int = Field(
        default=2,
        ge=0,
        le=10,
        description="Maximum questions per turn (0 = no questions, 1-10 = limited questions)"
    )

    assume_defaults: bool = Field(
        default=False,
        description="Whether to assume defaults for missing parameters (Cursor-style)"
    )

    require_assumptions_list: bool = Field(
        default=True,
        description="When max_questions_per_turn=0, require output of assumptions[] (列出替用戶補的預設)"
    )


class OutputContract(BaseModel):
    """Output Contract - 輸出契約"""

    # Coding output contract
    coding_style: CodingStyle = Field(
        default=CodingStyle.PATCH_FIRST,
        description="Coding output style: patch_first (Cursor-style), explain_first, code_only"
    )

    # Writing output contract
    writing_style: WritingStyle = Field(
        default=WritingStyle.STRUCTURE_FIRST,
        description="Writing output style: structure_first, draft_first, both"
    )

    # General output contract
    minimize_explanation: bool = Field(
        default=False,
        description="Minimize explanation text (Cursor-style: less talk, more action)"
    )

    show_rationale_level: RationaleLevel = Field(
        default=RationaleLevel.BRIEF,
        description="Output rationale level: none (no explanation), brief (key decisions), detailed (full decision log)"
    )

    include_decision_log: bool = Field(
        default=False,
        description="Include decision log: assumptions, risks, next steps"
    )


class ToolPolicy(BaseModel):
    """Tool Policy - 工具政策（階段 2 擴展版）"""

    allowlist: Optional[List[str]] = Field(
        None,
        description="Allowed tool types/capability codes (workspace-level)"
    )

    denylist: Optional[List[str]] = Field(
        None,
        description="Denied tool types/capability codes (workspace-level)"
    )

    # 階段 2 擴展欄位
    require_approval_for_capabilities: List[str] = Field(
        default_factory=list,
        description="Capability codes that require explicit approval (使用 capability_code)"
    )

    allow_parallel_tool_calls: bool = Field(
        default=False,
        description="Allow parallel tool calls (for performance optimization)"
    )

    max_tool_call_chain: int = Field(
        default=5,
        ge=1,
        le=20,
        description="Maximum tool call chain length (prevent infinite loops)"
    )


class ConfirmationPolicy(BaseModel):
    """Confirmation Policy - 確認政策"""

    # Risk-based confirmation
    auto_read: bool = Field(
        default=True,
        description="Auto-execute read-only operations (risk_class='readonly')"
    )

    confirm_soft_write: bool = Field(
        default=True,
        description="Require confirmation for soft_write operations (risk_class='soft_write')"
    )

    confirm_external_write: bool = Field(
        default=True,
        description="Require confirmation for external_write operations (risk_class='external_write')"
    )

    # Confirmation format
    confirmation_format: ConfirmationFormat = Field(
        default=ConfirmationFormat.LIST_CHANGES,
        description="Confirmation format: list_changes (列出變更 → 等你確認), summary, detailed"
    )

    # Confirmation scope
    require_explicit_confirm: bool = Field(
        default=True,
        description="Require explicit user confirmation (not just implicit acceptance)"
    )


# ==================== 階段 2 擴展模型 ====================

class LoopBudget(BaseModel):
    """Loop Budget - 迭代預算（對應 Google ADK 的 LoopAgent）"""

    max_iterations: int = Field(
        default=10,
        ge=1,
        le=100,
        description="Maximum iterations for loop-based agents (類似 LangGraph 的 recursion_limit)"
    )

    max_turns: int = Field(
        default=20,
        ge=1,
        le=200,
        description="Maximum conversation turns per session"
    )

    max_steps: int = Field(
        default=50,
        ge=1,
        le=500,
        description="Maximum execution steps (類似 LangGraph 的 remaining_steps)"
    )

    max_tool_calls: int = Field(
        default=30,
        ge=1,
        le=300,
        description="Maximum tool calls per execution"
    )

    token_budget: Optional[int] = Field(
        None,
        description="Token budget limit (None = unlimited)"
    )

    cost_budget: Optional[float] = Field(
        None,
        description="Cost budget limit in USD (None = unlimited)"
    )

    time_budget_seconds: Optional[int] = Field(
        None,
        description="Time budget in seconds (None = unlimited)"
    )


class StopConditions(BaseModel):
    """Stop Conditions - 停止條件"""

    # Definition of Done
    definition_of_done: Optional[List[str]] = Field(
        None,
        description="Definition of Done criteria (e.g., ['lint passed', 'tests passed', 'docs updated'])"
    )

    # Rule-based score calculation (修正：移除純模型自評的 confidence_threshold)
    proceed_score_calculation: Dict[str, Any] = Field(
        default_factory=lambda: {
            "required_fields_missing_penalty": -0.3,  # 每缺一個必填欄位扣 0.3
            "risk_level_multiplier": {
                "readonly": 1.0,
                "soft_write": 0.7,
                "external_write": 0.4
            },
            "reversible_bonus": 0.2,  # 可逆操作加分
            "minimum_score": 0.6  # 最低分數閾值
        },
        description="Rule-based score calculation for auto-proceed decision"
    )

    # Optional: PolicyEvaluator (階段 2)
    use_policy_evaluator: bool = Field(
        default=False,
        description="Use separate PolicyEvaluator (small model) to evaluate proceed | ask | block"
    )

    # Consistency check (critic agreement)
    require_critic_agreement: bool = Field(
        default=False,
        description="Require critic agent agreement before stopping"
    )

    # Retry limits
    max_retries: int = Field(
        default=3,
        ge=0,
        le=10,
        description="Maximum retry attempts on failure"
    )

    # Error threshold
    max_errors: int = Field(
        default=5,
        ge=1,
        le=20,
        description="Maximum errors before stopping"
    )

    # Early stopping conditions
    early_stop_on_success: bool = Field(
        default=True,
        description="Stop early if success criteria met"
    )


class QualityGates(BaseModel):
    """Quality Gates - 品質闖關"""

    # Code quality
    require_lint: bool = Field(
        default=False,
        description="Require linting to pass before completion"
    )

    require_tests: bool = Field(
        default=False,
        description="Require tests to pass before completion"
    )

    # Documentation
    require_docs: bool = Field(
        default=False,
        description="Require documentation updates"
    )

    # Change tracking
    require_changelist: bool = Field(
        default=True,
        description="Require change list before external writes"
    )

    require_rollback_plan: bool = Field(
        default=False,
        description="Require rollback plan for high-risk operations"
    )

    # Citation (for research workspaces)
    require_citations: bool = Field(
        default=False,
        description="Require source citations (for research workspaces). When enabled, output template must include citation block."
    )

    citation_template: Optional[str] = Field(
        None,
        description="Fixed citation template block (e.g., '## References\n\n...')"
    )


class SharedStatePolicy(BaseModel):
    """Shared State Policy - 共享狀態與記憶寫入規則"""

    # Memory write rules
    memory_event_types: List[str] = Field(
        default_factory=lambda: ["intents", "artifacts", "decisions"],
        description="Event types to write to long-term memory"
    )

    redact_fields: List[str] = Field(
        default_factory=lambda: ["api_keys", "passwords", "tokens"],
        description="Fields to redact before writing to long-term memory"
    )

    # 保留向後兼容（deprecated）
    write_to_long_term_memory: Optional[List[str]] = Field(
        None,
        description="[Deprecated] Use memory_event_types instead"
    )

    write_to_session_state: List[str] = Field(
        default_factory=lambda: ["context", "intermediate_results"],
        description="What to write to session state (temporary)"
    )

    # Summary triggers
    summarize_on_turn_count: Optional[int] = Field(
        None,
        description="Summarize context after N turns (None = never)"
    )

    summarize_on_token_count: Optional[int] = Field(
        None,
        description="Summarize context after N tokens (None = never)"
    )

    # RAG switching
    switch_rag_on_topic_change: bool = Field(
        default=False,
        description="Switch RAG source on topic change"
    )


class RecoveryPolicy(BaseModel):
    """Recovery Policy - 恢復策略"""

    # Retry strategy
    retry_on_failure: bool = Field(
        default=True,
        description="Retry on failure"
    )

    retry_strategy: Literal["immediate", "exponential_backoff", "ask_user"] = Field(
        default="exponential_backoff",
        description="Retry strategy"
    )

    # Fallback strategy
    fallback_on_error: bool = Field(
        default=True,
        description="Fallback to simpler approach on error"
    )

    fallback_mode: Literal["qa_only", "readonly", "ask_user"] = Field(
        default="ask_user",
        description="Fallback mode when error occurs"
    )

    # Escalation
    escalate_to_human_on: List[str] = Field(
        default_factory=lambda: ["external_write", "deletion", "deployment"],
        description="Escalate to human on these operations"
    )


class TopologyRouting(BaseModel):
    """Topology Routing - 拓撲與路由（僅定義傳球規則，不定義球員名單）"""

    # Agent routing rules（引用 Playbook 中定義的 agent_id）
    agent_routing_rules: Dict[str, List[str]] = Field(
        default_factory=dict,
        description="Agent routing rules: {from_agent_id: [to_agent_id1, to_agent_id2, ...]}. "
                    "agent_id 必須對應到 Playbook 中定義的 agent roster"
    )

    # Workflow patterns
    default_pattern: Literal["sequential", "loop", "parallel", "hierarchical"] = Field(
        default="sequential",
        description="Default workflow pattern"
    )

    # Pattern-specific config
    pattern_config: Dict[str, Any] = Field(
        default_factory=dict,
        description="Pattern-specific configuration"
    )


# ==================== Main Model ====================

class WorkspaceRuntimeProfile(BaseModel):
    """Workspace Runtime Profile - 工作區執行檔"""

    # Mode 預設值
    default_mode: ExecutionMode = Field(
        default=ExecutionMode.QA,
        description="Default execution mode: qa/execution/hybrid"
    )

    # Interaction Budget
    interaction_budget: InteractionBudget = Field(
        default_factory=lambda: InteractionBudget(),
        description="Interaction budget configuration"
    )

    # Output Contract
    output_contract: OutputContract = Field(
        default_factory=lambda: OutputContract(),
        description="Output contract configuration"
    )

    # Risk Posture / Confirmation Policy
    confirmation_policy: ConfirmationPolicy = Field(
        default_factory=lambda: ConfirmationPolicy(),
        description="Confirmation policy for risk management"
    )

    # Tool Policy
    tool_policy: ToolPolicy = Field(
        default_factory=lambda: ToolPolicy(),
        description="Tool policy configuration"
    )

    # 階段 2 擴展字段（Phase 2: 完整版本）
    # Loop Budget - 迭代預算
    loop_budget: "LoopBudget" = Field(
        default_factory=lambda: LoopBudget(),
        description="Loop budget configuration (階段 2)"
    )

    # Stop Conditions - 停止條件
    stop_conditions: "StopConditions" = Field(
        default_factory=lambda: StopConditions(),
        description="Stop conditions configuration (階段 2)"
    )

    # Quality Gates - 品質闖關
    quality_gates: "QualityGates" = Field(
        default_factory=lambda: QualityGates(),
        description="Quality gates configuration (階段 2)"
    )

    # Shared State Policy - 共享狀態與記憶寫入規則
    shared_state_policy: "SharedStatePolicy" = Field(
        default_factory=lambda: SharedStatePolicy(),
        description="Shared state policy configuration (階段 2)"
    )

    # Recovery Policy - 恢復策略
    recovery_policy: "RecoveryPolicy" = Field(
        default_factory=lambda: RecoveryPolicy(),
        description="Recovery policy configuration (階段 2)"
    )

    # Topology Routing - 拓撲與路由（多 Agent Orchestration）
    topology_routing: Optional["TopologyRouting"] = Field(
        None,
        description="Topology routing configuration (階段 2, optional for single-agent workspaces)"
    )

    # Metadata
    metadata: Dict[str, Any] = Field(
        default_factory=dict,
        description="Additional metadata"
    )

    # Schema versioning
    schema_version: str = Field(
        default="2.0",
        description="Schema version for backward compatibility (metadata JSON storage). "
                    "1.0 = MVP (5 fields), 2.0 = Phase 2 (extended with loop_budget, stop_conditions, etc.)"
    )

    def ensure_phase2_fields(self) -> "WorkspaceRuntimeProfile":
        """
        确保 Phase 2 字段已初始化（向后兼容：从 Phase 1 升级）

        Returns:
            WorkspaceRuntimeProfile with Phase 2 fields initialized
        """
        if self.loop_budget is None:
            self.loop_budget = LoopBudget()
        if self.stop_conditions is None:
            self.stop_conditions = StopConditions()
        if self.quality_gates is None:
            self.quality_gates = QualityGates()
        if self.shared_state_policy is None:
            self.shared_state_policy = SharedStatePolicy()
        if self.recovery_policy is None:
            self.recovery_policy = RecoveryPolicy()
        # Update schema version
        if self.schema_version == "1.0":
            self.schema_version = "2.0"
        return self

    # Audit fields
    updated_by: Optional[str] = Field(
        None,
        description="User ID who last updated this profile"
    )

    updated_reason: Optional[str] = Field(
        None,
        description="Reason for update (for governance/audit)"
    )

    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

    # Resolved mode property
    @property
    def resolved_mode(self) -> ExecutionMode:
        """Resolved mode: runtime_profile.default_mode 優先於 workspace.execution_mode"""
        return self.default_mode

    def sync_to_workspace(self, workspace: "Workspace") -> "Workspace":
        """同步 Runtime Profile 到 Workspace（保持向後兼容）"""
        workspace.execution_mode = self.default_mode.value
        return workspace

    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat(),
            ExecutionMode: lambda v: v.value,
            RationaleLevel: lambda v: v.value,
            CodingStyle: lambda v: v.value,
            WritingStyle: lambda v: v.value,
            ConfirmationFormat: lambda v: v.value,
        }

