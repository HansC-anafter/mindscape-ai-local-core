"""
Control Knob Model

Defines the knob-based control system for LLM response patterns.
Based on CONTROL_KNOB_DESIGN_SPEC.md v2.4
"""

from typing import Optional, List, Dict, Literal
from enum import Enum
from pydantic import BaseModel, Field, validator


# ==================== Enums ====================

class KnobType(str, Enum):
    """旋鈕類型"""
    HARD = "hard"  # Deterministic / Policy
    SOFT = "soft"  # Stylistic / Preference


class PromptPatchPosition(str, Enum):
    """Prompt Patch 注入位置"""
    SYSTEM_APPEND = "system_append"      # 追加到 system message 末尾（推薦）
    SYSTEM_PREPEND = "system_prepend"    # 插入到 system message 開頭
    CONTEXT_SECTION = "context_section"  # 插入到 context 區塊


# ==================== Sub-models ====================

class KnobAnchor(BaseModel):
    """旋鈕錨點"""
    value: int = Field(..., ge=0, le=100, description="錨點值")
    label: str = Field(..., description="錨點標籤")
    description: Optional[str] = Field(None, description="錨點描述")


class MasterValueRange(BaseModel):
    """主旋鈕值區間映射（避免字串解析 bug）"""
    min_value: int = Field(..., ge=0, le=100, description="區間最小值（含）")
    max_value: int = Field(..., ge=0, le=100, description="區間最大值（含）")
    slave_value: int = Field(..., ge=0, le=100, description="從屬旋鈕對應的值")

    @validator("max_value")
    def validate_range(cls, v, values):
        if "min_value" in values and v < values["min_value"]:
            raise ValueError("max_value must be >= min_value")
        return v


class PromptPatch(BaseModel):
    """Prompt 補丁（注入到 System 層，不污染 Assistant Output）"""
    template: str = Field(
        ...,
        description="Prompt 片段模板，支持 {value} 和 {anchor_label} 變量"
    )
    position: PromptPatchPosition = Field(
        default=PromptPatchPosition.SYSTEM_APPEND,
        description="注入位置（只允許 system 層，禁止 assistant output）"
    )
    condition: Optional[str] = Field(
        None,
        description="條件表達式（例如 'value > 50'）"
    )
    use_natural_language: bool = Field(
        default=True,
        description="使用自然語言而非 debug tag 格式"
    )


class ModelParamsDelta(BaseModel):
    """模型參數增量"""
    temperature_delta: Optional[float] = Field(None, description="Temperature 增量")
    top_p_delta: Optional[float] = Field(None, description="Top-p 增量")
    presence_penalty_delta: Optional[float] = Field(None, description="Presence penalty 增量")
    frequency_penalty_delta: Optional[float] = Field(None, description="Frequency penalty 增量")
    max_tokens_delta: Optional[int] = Field(None, description="Max tokens 增量")


class RuntimePolicyDelta(BaseModel):
    """運行時策略增量"""
    # Interaction Budget
    max_questions_per_turn_delta: Optional[int] = None
    assume_defaults_override: Optional[bool] = None

    # Confirmation Policy
    auto_read_override: Optional[bool] = None
    confirm_soft_write_override: Optional[bool] = None
    confirm_external_write_override: Optional[bool] = None

    # Retrieval
    retrieval_scope: Optional[str] = None


class CalibrationExample(BaseModel):
    """校準範例"""
    knob_value: int = Field(..., ge=0, le=100)
    input_example: str = Field(..., description="輸入範例")
    output_example: str = Field(..., description="輸出範例")
    explanation: Optional[str] = Field(None, description="說明")


# ==================== Main Models ====================

class ControlKnob(BaseModel):
    """控制旋鈕定義"""

    # Identity
    id: str = Field(..., description="旋鈕 ID（stable key）")
    label: str = Field(..., description="顯示標籤")
    description: Optional[str] = Field(None, description="旋鈕描述")
    icon: Optional[str] = Field(None, description="圖標（emoji 或 icon name）")

    # Type
    knob_type: KnobType = Field(
        default=KnobType.HARD,
        description="旋鈕類型"
    )

    # Range
    min_value: int = Field(default=0, ge=0, le=100)
    max_value: int = Field(default=100, ge=0, le=100)
    default_value: int = Field(default=50, ge=0, le=100)
    step: int = Field(default=10, ge=1, le=50, description="步進值")

    # Anchors（三段錨點）
    anchors: List[KnobAnchor] = Field(
        default_factory=lambda: [
            KnobAnchor(value=0, label="最小"),
            KnobAnchor(value=50, label="中等"),
            KnobAnchor(value=100, label="最大"),
        ],
        description="錨點定義（通常 3 個）"
    )

    # ==================== v2: 主從關係 ====================
    master_knob_id: Optional[str] = Field(
        None,
        description="主旋鈕 ID（如果此旋鈕是從屬旋鈕）"
    )
    is_locked_to_master: bool = Field(
        default=True,
        description="是否鎖定跟隨主旋鈕（用戶可解鎖獨立調整）"
    )
    # v2.1: 改用結構化 array，避免字串區間解析 bug
    master_value_mapping: Optional[List[MasterValueRange]] = Field(
        None,
        description="主旋鈕值 → 此旋鈕值的映射規則"
    )

    # ==================== v2: 參數互斥 ====================
    exclusive_param: Optional[str] = Field(
        None,
        description="此旋鈕獨佔的 model param（其他旋鈕不可動）"
    )

    # Effects（三層映射）
    prompt_patch: Optional[PromptPatch] = Field(
        None,
        description="Prompt 補丁（注入到 System 層）"
    )
    model_params_delta: Optional[ModelParamsDelta] = Field(
        None,
        description="模型參數增量"
    )
    runtime_policy_delta: Optional[RuntimePolicyDelta] = Field(
        None,
        description="運行時策略增量"
    )

    # Calibration
    calibration_examples: List[CalibrationExample] = Field(
        default_factory=list,
        description="校準範例（讓使用者理解旋鈕效果）"
    )

    # Metadata
    category: Optional[str] = Field(None, description="分類（用於 UI 分組）")
    is_advanced: bool = Field(default=False, description="是否為進階旋鈕")
    is_enabled: bool = Field(default=True, description="是否啟用")

    # Versioning
    version: str = Field(default="1.0.0", description="旋鈕定義版本")
    created_by: Optional[str] = Field(None, description="創建者（user/llm）")


class ControlProfile(BaseModel):
    """控制面板配置（旋鈕組合）"""

    # Identity
    id: str = Field(..., description="控制面板 ID")
    name: str = Field(..., description="控制面板名稱")
    description: Optional[str] = Field(None, description="描述")

    # Knobs
    knobs: List[ControlKnob] = Field(
        default_factory=list,
        description="旋鈕列表"
    )

    # Current Values
    knob_values: Dict[str, int] = Field(
        default_factory=dict,
        description="當前旋鈕值（knob_id -> value）"
    )

    # Preset
    preset_id: Optional[str] = Field(
        None,
        description="Preset ID（如果來自 preset）"
    )

    # Metadata
    workspace_id: Optional[str] = Field(None, description="Workspace ID")
    created_at: Optional[str] = Field(None, description="創建時間")
    updated_at: Optional[str] = Field(None, description="更新時間")

