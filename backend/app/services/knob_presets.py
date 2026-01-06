"""
Control Knob Presets and Core Knobs

Defines the 3 core presets and 4 core knobs based on CONTROL_KNOB_DESIGN_SPEC.md v2.4
"""

from backend.app.models.control_knob import (
    ControlKnob,
    ControlProfile,
    KnobType,
    KnobAnchor,
    PromptPatch,
    PromptPatchPosition,
    ModelParamsDelta,
    RuntimePolicyDelta,
    MasterValueRange,
    CalibrationExample,
)

# ==================== Core Knobs ====================

CORE_KNOBS = [
    # ==================== 1. 介入程度（主旋鈕）====================
    ControlKnob(
        id="intervention_level",
        label="介入程度",
        icon="🎯",
        knob_type=KnobType.HARD,
        anchors=[
            KnobAnchor(value=0, label="旁觀整理", description="只整理資訊，不做建議"),
            KnobAnchor(value=50, label="主動提案", description="主動提出建議和選項"),
            KnobAnchor(value=100, label="直接執行", description="直接產出可確認的草稿"),
        ],
        # v2.3: 縮短 prompt patch，細節用 runtime policy 驅動
        prompt_patch=PromptPatch(
            template="Mode: {anchor_label}. If missing info: ask up to {max_questions} questions.",
            position=PromptPatchPosition.SYSTEM_APPEND,
            use_natural_language=True
        ),
        # v2.3: 主要透過 policy 控制，不靠長 prompt
        runtime_policy_delta=RuntimePolicyDelta(
            assume_defaults_override=None,  # compiler 根據 value 動態設置
            max_questions_per_turn_delta=None  # 0-30 → 5, 31-70 → 2, 71-100 → 0
        ),
        calibration_examples=[
            CalibrationExample(
                knob_value=20,
                input_example="我有這些會議記錄",
                output_example="我看到 3 份會議記錄，主題分別是：\n1. 產品規劃（12/15）\n2. 技術架構（12/18）\n3. 進度檢討（12/22）",
                explanation="低介入：只整理，不建議下一步"
            ),
            CalibrationExample(
                knob_value=80,
                input_example="我有這些會議記錄",
                output_example="已幫你整理成週報草稿，請確認：\n\n## 本週重點\n1. 產品：確定 MVP 範圍\n2. 技術：選定 FastAPI 架構\n\n## 下週計劃\n- 完成 API 設計\n\n[確認] [修改]",
                explanation="高介入：直接產出草稿，帶確認按鈕"
            ),
        ],
        category="core",
        is_advanced=False
    ),

    # ==================== 2. 收斂度（獨佔 temperature）====================
    ControlKnob(
        id="convergence",
        label="收斂度",
        icon="🎯",
        knob_type=KnobType.SOFT,
        anchors=[
            KnobAnchor(value=0, label="發散探索", description="給出多種可能性"),
            KnobAnchor(value=50, label="平衡", description="探索後收斂"),
            KnobAnchor(value=100, label="強制收斂", description="直接給決策建議"),
        ],
        prompt_patch=PromptPatch(
            template="Response convergence level: {value}%.\n- Low (0-30): Explore broadly, provide multiple perspectives and options.\n- Medium (31-70): Explore, then synthesize into 2-3 recommendations.\n- High (71-100): Converge quickly to a single actionable recommendation.",
            position=PromptPatchPosition.SYSTEM_APPEND,
            use_natural_language=True
        ),
        model_params_delta=ModelParamsDelta(
            # 發散(0) → temp +0.3；收斂(100) → temp -0.3
            # 設為 None 讓編譯器走動態計算公式
            temperature_delta=None  # 動態計算：(50 - value) / 166.67
        ),
        # v2: 獨佔 temperature
        exclusive_param="temperature",
        category="core",
        is_advanced=False
    ),

    # ==================== 3. 輸出密度（Prompt + Output Contract）====================
    # v2.3: max_tokens 由 compiler 根據 verbosity 值寫入 model_params（路線 A）
    ControlKnob(
        id="verbosity",
        label="輸出密度",
        icon="📝",
        knob_type=KnobType.SOFT,
        anchors=[
            KnobAnchor(value=0, label="一句話", description="極簡回覆"),
            KnobAnchor(value=50, label="條列", description="條列式回覆"),
            KnobAnchor(value=100, label="完整稿", description="可直接使用的完整內容"),
        ],
        # v2.3: 只用 prompt patch + output contract（不直接設 runtime_policy）
        prompt_patch=PromptPatch(
            template="Output verbosity level: {value}%.\n- Low (0-30): Respond in ONE sentence only. No elaboration.\n- Medium (31-70): Use bullet points (3-7 items). No paragraphs.\n- High (71-100): Provide a complete draft with sections:\n  - Summary\n  - Key points\n  - Details\n  - Next steps (if applicable)",
            position=PromptPatchPosition.SYSTEM_APPEND,
            use_natural_language=True
        ),
        # v2.3: max_tokens 由 compiler 處理，寫入 model_params
        model_params_delta=ModelParamsDelta(
            # compiler 會根據 verbosity 值動態計算 max_tokens
            # 0-30 → 100, 31-70 → 500, 71-100 → 2000
        ),
        # ⚠️ v2.3: verbosity 擁有 max_tokens 的主控權
        exclusive_param="max_tokens",
        category="core",
        is_advanced=False
    ),

    # ==================== 4. 檢索半徑 ====================
    ControlKnob(
        id="retrieval_radius",
        label="檢索半徑",
        icon="🔍",
        knob_type=KnobType.HARD,
        anchors=[
            KnobAnchor(value=0, label="本對話", description="只看當前對話"),
            KnobAnchor(value=50, label="本 Workspace", description="看整個 workspace 的內容"),
            KnobAnchor(value=100, label="跨 Workspace", description="看所有有權限的 workspace"),
        ],
        runtime_policy_delta=RuntimePolicyDelta(
            retrieval_scope=None  # 根據 value 設置
        ),
        # v2: 跨 workspace 時需要在 UI/trace 顯示使用了哪些 workspace
        category="core",
        is_advanced=False,
        calibration_examples=[
            CalibrationExample(
                knob_value=100,
                input_example="找一下之前的設計文檔",
                output_example="從以下 workspace 找到相關文檔：\n- [設計專案] 品牌識別設計.md\n- [技術專案] API 設計規範.md\n\n是否展開查看？",
                explanation="跨 workspace 時，明確顯示資料來源"
            ),
        ],
    ),
]

# ==================== Slave Knobs (從屬旋鈕) ====================

SLAVE_KNOBS = [
    # ==================== 從屬於 intervention_level ====================
    ControlKnob(
        id="tool_action_threshold",
        label="工具動作門檻",
        icon="🔧",
        knob_type=KnobType.HARD,
        is_advanced=True,  # 折疊到進階
        anchors=[
            KnobAnchor(value=0, label="只建議", description="只說可以做什麼"),
            KnobAnchor(value=50, label="提草稿", description="準備可執行草稿"),
            KnobAnchor(value=100, label="自動執行", description="直接執行 readonly"),
        ],
        runtime_policy_delta=RuntimePolicyDelta(
            auto_read_override=None,
            confirm_soft_write_override=None,
        ),
        # v2: 從屬於 intervention_level
        master_knob_id="intervention_level",
        is_locked_to_master=True,  # 預設鎖定跟隨
        # v2.1: 結構化 array，避免字串區間解析 bug
        master_value_mapping=[
            MasterValueRange(min_value=0, max_value=30, slave_value=20),   # 低介入 → 只建議
            MasterValueRange(min_value=31, max_value=70, slave_value=50),  # 中介入 → 提草稿
            MasterValueRange(min_value=71, max_value=100, slave_value=80), # 高介入 → 自動執行
        ],
        category="intervention"
    ),

    ControlKnob(
        id="confirmation_threshold",
        label="確認門檻",
        icon="✅",
        knob_type=KnobType.HARD,
        is_advanced=True,
        anchors=[
            KnobAnchor(value=0, label="寬鬆", description="只確認高風險操作"),
            KnobAnchor(value=50, label="外部確認", description="外部操作需確認"),
            KnobAnchor(value=100, label="每步確認", description="每個操作都確認"),
        ],
        runtime_policy_delta=RuntimePolicyDelta(
            confirm_external_write_override=None,
        ),
        # v2: 從屬於 intervention_level（反向關係）
        master_knob_id="intervention_level",
        is_locked_to_master=True,
        # v2.1: 結構化 array（反向：高介入 = 低確認門檻）
        master_value_mapping=[
            MasterValueRange(min_value=0, max_value=30, slave_value=80),   # 低介入 → 高確認門檻
            MasterValueRange(min_value=31, max_value=70, slave_value=50),  # 中介入 → 中等確認
            MasterValueRange(min_value=71, max_value=100, slave_value=20), # 高介入 → 低確認門檻
        ],
        category="intervention"
    ),
]

# ==================== Advanced Knobs (進階旋鈕) ====================

ADVANCED_KNOBS = [
    # ==================== v2: boldness 用 presence_penalty，不動 temperature ====================
    ControlKnob(
        id="boldness",
        label="保守↔大膽",
        icon="🎲",
        knob_type=KnobType.SOFT,
        is_advanced=True,
        anchors=[
            KnobAnchor(value=0, label="保守", description="謹慎、安全的建議"),
            KnobAnchor(value=50, label="平衡"),
            KnobAnchor(value=100, label="大膽", description="創新、突破性建議"),
        ],
        prompt_patch=PromptPatch(
            template="Creativity stance: {anchor_label}.\nAt high boldness, propose breakthrough ideas even if unconventional.\nAt low boldness, stick to proven, safe approaches.",
            position=PromptPatchPosition.SYSTEM_APPEND,
            use_natural_language=True
        ),
        model_params_delta=ModelParamsDelta(
            # v2: 只動 presence_penalty，不動 temperature（避免與 convergence 衝突）
            # 設為 None 讓編譯器走動態計算公式
            presence_penalty_delta=None  # 動態計算：(value - 50) / 125
        ),
        exclusive_param="presence_penalty",  # 獨佔
        category="style"
    ),

    ControlKnob(
        id="uncertainty_marking",
        label="不確定標註",
        icon="❓",
        knob_type=KnobType.HARD,
        is_advanced=True,
        anchors=[
            KnobAnchor(value=0, label="不標", description="不標註不確定性"),
            KnobAnchor(value=50, label="標關鍵", description="標註關鍵假設"),
            KnobAnchor(value=100, label="完整標", description="標註所有假設和不確定性"),
        ],
        prompt_patch=PromptPatch(
            template="Uncertainty marking level: {value}%.\n- Low: Provide answers directly without hedging.\n- Medium: Mark key assumptions with \"⚠️ Assumption: ...\"\n- High: Mark all uncertainties, assumptions, and information gaps.",
            position=PromptPatchPosition.SYSTEM_APPEND,
            use_natural_language=True
        ),
        # v2: 改名自 evidence_strength，避免誤以為要上網查
        category="quality"
    ),

    ControlKnob(
        id="tone_warmth",
        label="冷靜↔有溫度",
        icon="❤️",
        knob_type=KnobType.SOFT,
        is_advanced=True,
        anchors=[
            KnobAnchor(value=0, label="冷靜專業"),
            KnobAnchor(value=50, label="中性"),
            KnobAnchor(value=100, label="溫暖關懷"),
        ],
        prompt_patch=PromptPatch(
            template="Communication tone: {anchor_label}.",
            position=PromptPatchPosition.SYSTEM_APPEND,
            use_natural_language=True
        ),
        category="style"
    ),

    ControlKnob(
        id="lens_intensity",
        label="心智濾鏡強度",
        icon="🔮",
        knob_type=KnobType.SOFT,
        is_advanced=True,
        anchors=[
            KnobAnchor(value=0, label="不套 Lens"),
            KnobAnchor(value=50, label="輕度套用"),
            KnobAnchor(value=100, label="強制對齊"),
        ],
        prompt_patch=PromptPatch(
            template="Mind-Lens intensity: {value}%.\n- Low: No lens filtering.\n- Medium: Light lens application.\n- High: Strong lens alignment required.",
            position=PromptPatchPosition.SYSTEM_APPEND,
            use_natural_language=True
        ),
        category="lens"
    ),
]

# ==================== Presets ====================

PRESET_OBSERVER = ControlProfile(
    id="observer",
    name="整理模式",
    description="只整理資訊，不主動建議",
    knobs=CORE_KNOBS + SLAVE_KNOBS + ADVANCED_KNOBS,  # 包含進階旋鈕
    knob_values={
        "intervention_level": 20,   # 低介入
        "convergence": 30,          # 偏發散
        "verbosity": 50,            # 條列
        "retrieval_radius": 50,     # 本 workspace
        # 進階旋鈕使用預設值
    },
    preset_id="observer"
)

PRESET_ADVISOR = ControlProfile(
    id="advisor",
    name="提案模式",
    description="主動提出建議和選項",
    knobs=CORE_KNOBS + SLAVE_KNOBS + ADVANCED_KNOBS,  # 包含進階旋鈕
    knob_values={
        "intervention_level": 60,   # 中高介入
        "convergence": 60,          # 偏收斂
        "verbosity": 50,            # 條列
        "retrieval_radius": 50,     # 本 workspace
        # 進階旋鈕使用預設值
    },
    preset_id="advisor"
)

PRESET_EXECUTOR = ControlProfile(
    id="executor",
    name="可直接交付",
    description="直接產出可確認的草稿",
    knobs=CORE_KNOBS + SLAVE_KNOBS + ADVANCED_KNOBS,  # 包含進階旋鈕
    knob_values={
        "intervention_level": 85,   # 高介入
        "convergence": 80,          # 強收斂
        "verbosity": 90,            # 完整稿
        "retrieval_radius": 50,     # 本 workspace
        # 進階旋鈕使用預設值
    },
    preset_id="executor"
)

# All presets
PRESETS = {
    "observer": PRESET_OBSERVER,
    "advisor": PRESET_ADVISOR,
    "executor": PRESET_EXECUTOR,
}

