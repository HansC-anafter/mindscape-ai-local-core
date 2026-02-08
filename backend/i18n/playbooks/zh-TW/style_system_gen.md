---
playbook_code: style_system_gen
version: 1.0.0
capability_code: web_generation
name: 樣式系統生成
description: |
  從 site_spec.yaml 的 theme 配置生成完整的樣式系統，包括 CSS 變量、Tailwind 配置和全局樣式。
  這是完整網站生成流程的第二步，為後續組件生成提供統一的樣式基礎。
tags:
  - web
  - styling
  - css
  - tailwind
  - design-system

kind: user_workflow
interaction_mode:
  - conversational
  - needs_review
visible_in:
  - workspace_tools_panel
  - workspace_playbook_menu

required_tools:
  - filesystem_write_file
  - filesystem_read_file
  - cloud_capability.call
  - visual_lens_list
  - visual_lens_get

language_strategy: model_native
locale: zh-TW
supported_locales:
  - zh-TW
  - en
default_locale: zh-TW
auto_localize: true

entry_agent_type: coder
icon: 🎨
---

# 樣式系統生成 - SOP

## 目標

從 `spec/site_spec.yaml` 的 `theme` 配置生成完整的樣式系統，包括：
- CSS 變量文件（`styles/variables.css`）
- Tailwind 配置文件（`tailwind.config.js`）
- 全局樣式文件（`styles/global.css`）

輸出到 Project Sandbox 的 `styles/` 目錄。

**工作流程說明**：
- 這是完整網站生成流程的**第二步**：生成樣式系統
- 必須在 `site_spec_generation` playbook 之後執行
- 生成的樣式系統將被後續的組件生成和頁面組裝使用

## 執行步驟

### Phase 0: 檢查 Project Context

**執行順序**：
1. 步驟 0.0: 取得 Brand Context
2. 步驟 0.1: 檢查是否有活躍的 web_page 或 website project
3. 步驟 0.2: 獲取 Project Sandbox 路徑
4. 步驟 0.3: 讀取網站規格文檔
5. 步驟 0.4: 檢查並取得 Visual Lens（如果存在）

**注意**：步驟 0.3 和 0.4 可以按順序執行，但**關鍵是在 Phase 1 使用 theme 配置時，如果存在 Visual Lens，必須優先使用 Visual Lens 生成的 theme 配置，而不是直接使用 site_spec.yaml 中的 theme 配置！**

#### 步驟 0.0: 取得 Brand Context

在開始生成樣式系統之前，先取得品牌的基礎設定，特別是視覺識別相關的規範。

**取得品牌設定**：

```tool
cloud_capability.call
capability: brand_identity
endpoint: context/get
params:
  workspace_id: {workspace_id}
  auto_generate: true
  min_data_required: true
```

**Brand Context 的使用指引**：

如果 `has_brand_context = true`，在後續生成樣式系統時，請參考：

1. **品牌視覺方向**：
   - 參考 `brand_mi.vision` 和 `brand_mi.worldview` 來決定整體視覺調性
   - 參考 `brand_mi.values` 來選擇符合品牌價值的色彩和風格

2. **品牌個性**：
   - 參考 `brand_personas` 來理解品牌要傳達的個性
   - 根據品牌個性選擇字體風格（例如：專業、親和、創新等）

3. **品牌故事主軸**：
   - 參考 `brand_storylines` 來決定視覺風格要呼應的故事主題

4. **視覺識別規範**：
   - 如果有 `brand_vi_rules`，優先使用品牌視覺規範中的色彩、字體、間距等設定
   - 如果沒有 `brand_vi_rules`，基於 `brand_mi` 推導合理的視覺規範

**Brand Context 來源提示**：

- 如果 `metadata.source = "existing_artifacts"`：使用現有的品牌設定
- 如果 `metadata.source = "auto_generated"`：
  - 這些品牌設定是基於現有數據自動生成的
  - 建議後續執行 `cis_mind_identity` 或 `cis_visual_identity` playbook 建立更完整的品牌視覺定義
  - 當前生成的樣式系統可以基於這些臨時設定開始，後續可以調整

**如果沒有 Brand Context**：

如果 `has_brand_context = false`：
- 提示用戶：「建議先執行 `cis_mind_identity` playbook 建立品牌設定，這樣生成的樣式系統會更符合品牌調性。」
- 可以繼續生成，但提醒「未參考品牌設定，後續可能需要調整」

#### 步驟 0.1: 檢查是否有活躍的 web_page 或 website project
- 檢查 execution context 中是否有 `project_id`
- 如果有，確認 project type 為 `web_page` 或 `website`
- 如果沒有，提示用戶需要先創建 project

#### 步驟 0.2: 獲取 Project Sandbox 路徑
- 使用 `project_sandbox_manager.get_sandbox_path()` 獲取 sandbox 路徑
- Sandbox 路徑結構：`sandboxes/{workspace_id}/{project_type}/{project_id}/`
- 確保 `styles/` 目錄存在

#### 步驟 0.3: 讀取網站規格文檔
- 讀取 `spec/site_spec.yaml`（從 `site_spec_generation` playbook 生成）
- 如果不存在，提示用戶需要先執行 `site_spec_generation` playbook
- 解析網站規格，提取 `theme` 配置

#### 步驟 0.4: 檢查並取得 Visual Lens（如果存在）

**檢查是否有 Visual Lens**：

**必須**使用 `visual_lens_list` 工具查詢 workspace 中的 Visual Lens：

```tool
visual_lens_list
workspace_id: {workspace_id}
limit: 10
```

**如果存在 Visual Lens**（即使只有一個，也必須使用）：

1. **取得最新的 Visual Lens**（選擇列表中的第一個，或使用指定的 lens_id）：
   ```tool
   visual_lens_get
   workspace_id: {workspace_id}
   lens_id: {lens_id}  # 使用 visual_lens_list 返回的第一個 lens_id，或最新的
   ```

   **注意**：如果 `visual_lens_list` 返回了任何 Visual Lens，**必須**使用它，不要跳過此步驟！

2. **解析 Visual Lens Schema**：
   - `visual_lens_get` 返回的字典包含 `schema_data` 字段
   - 保存 `schema_data` 供後續使用（不需要在 Python 中轉換，直接使用字典格式）

3. **執行 Theme Routing**（**必須執行**）：
   - **必須**調用 `cloud_capability.call` 工具執行 Theme Routing：
     ```tool
     cloud_capability.call
     capability: web_generation
     endpoint: theme-routing/get-routed-theme
     params:
       workspace_id: {workspace_id}
       visual_lens: {schema_data}  # 從 visual_lens_get 獲取的 schema_data（整個字典）
     ```
   - 記錄返回的 `theme_id`（例如：`zen_wellness`, `minimal_clean_saas`）
   - 記錄返回的 `theme` 對象（完整的 theme 配置字典）

4. **執行 Token Synthesis**（**必須執行**）：
   - **必須**調用 `cloud_capability.call` 工具執行 Token Synthesis：
     ```tool
     cloud_capability.call
     capability: web_generation
     endpoint: token-synthesis/synthesize-tokens
     params:
       workspace_id: {workspace_id}
       visual_lens: {schema_data}  # 從 visual_lens_get 獲取的 schema_data
       theme: {routed_theme}  # 從 Theme Routing 獲取的 theme 字典（不是 theme_id）
       site_type: "website"  # 從 site_spec.yaml 讀取的 project_type，或默認 "website"
       sections: []  # 可選，從 site_spec.yaml 讀取的 sections 列表
       tone: "professional"  # 可選，根據品牌或項目類型推導，默認 "professional"
     ```
   - 記錄返回的 `style_schema`（WebStyleSchemaV1 格式字典）
   - 從返回的 `theme_config` 字段提取，這就是 `synthesized_theme_config`（用於後續生成樣式文件）

**輸出**：
- `has_visual_lens`: true/false
- `visual_lens`: Visual Lens 數據（如果存在）
- `routed_theme_id`: 選擇的 theme ID（如果存在）
- `synthesized_theme_config`: 合成的 ThemeConfig（如果存在）

**如果沒有 Visual Lens**：
- `has_visual_lens = false`
- 後續使用 site_spec 中的 theme 配置或預設值

### Phase 1: 解析 Theme 配置

**⚠️ 重要：在 Phase 1 中，如果步驟 0.4 發現了 Visual Lens，必須優先使用 Visual Lens 生成的 theme 配置，而不是直接使用 site_spec.yaml 中的 theme 配置！**

#### 步驟 1.1: 讀取 site_spec.yaml
**必須**使用 `filesystem_read_file` 工具讀取網站規格文檔：

- **文件路徑**：`spec/site_spec.yaml`（在 Project Sandbox 中）
- **完整路徑**：`sandboxes/{workspace_id}/{project_type}/{project_id}/spec/site_spec.yaml`

**注意**：即使讀取了 site_spec.yaml，如果存在 Visual Lens，**必須優先使用 Visual Lens 生成的 theme 配置**（見步驟 1.3）。

#### 步驟 1.2: 提取 Theme 配置
從 `site_spec.yaml` 中提取 `theme` 區塊：
- `theme.colors`: 色彩方案（primary, secondary, accent, neutral, semantic）
- `theme.typography`: 字體配置（heading_font, body_font, accent_font, type_scale, line_heights）
- `theme.spacing`: 間距尺度
- `theme.breakpoints`: 響應式斷點

#### 步驟 1.3: 使用 Token Synthesis 的 Theme 配置（如果存在 Visual Lens）

**⚠️ 關鍵判斷：如果步驟 0.4 發現了 Visual Lens 並成功執行了 Theme Routing 和 Token Synthesis，則 `has_visual_lens = true` 且 `synthesized_theme_config` 存在**：

**如果 `has_visual_lens = true` 且 `synthesized_theme_config` 存在**：

**優先使用 Token Synthesis 的完整 theme 配置**：

1. **使用合成的 ThemeConfig**：
   - `theme_config = synthesized_theme_config`
   - 這個配置已經包含：
     - **視覺 tokens**（從 Visual Lens 提取 70%）：palette, imagery, mood, subject
     - **設計系統 tokens**（從 Theme 取得 80%）：typography, radius, shadow, spacing, grid, motion

2. **驗證配置完整性**：
   - 確保所有必需的字段都存在（colors, typography, spacing, breakpoints）
   - 如果缺少任何字段，從 site_spec 或 Brand Context 補充

3. **記錄來源**：
   - 標記 theme 配置來源為 "Visual Lens + Theme Routing + Token Synthesis"
   - 記錄使用的 theme_id（例如：`zen_wellness`）

**如果沒有 Visual Lens**：

使用步驟 1.4 的邏輯（整合 Brand Context 和 site_spec）。

#### 步驟 1.4: 整合 Brand Context 和 site_spec（如果沒有 Visual Lens）

**如果 `has_visual_lens = false`**：

確保所有必需的 theme 配置都存在：
- **優先級順序**：
  1. Brand Context（如果有 `brand_vi_rules`）
  2. Brand MI 推導（如果有 `brand_mi`）
  3. site_spec 中的 theme 配置
  4. 合理的預設值
- 記錄使用的來源（Brand Context / site_spec / 預設值），供用戶審核

**如果 `has_visual_lens = true` 但需要補充**：

如果 Token Synthesis 的配置缺少某些字段，按以下優先級補充：
1. Brand Context（如果有 `brand_vi_rules`）
2. site_spec 中的 theme 配置
3. 合理的預設值

#### 步驟 1.5: 檢測缺失的 Tokens 並生成 Stitch Prompt Pack（半自動引導）

**檢測缺失的 Tokens**：

檢查 `final_theme_config` 中是否有缺失或使用預設值的字段：

1. **檢測缺失的 Typography**：
   - 如果 `typography.heading_font` 或 `typography.body_font` 是預設值
   - 如果 `typography.type_scale` 不完整（缺少 h1, h2, h3, body）
   - 如果 `typography.line_heights` 不完整

2. **檢測缺失的 Spacing**：
   - 如果 `spacing` 是預設值 `[4, 8, 12, 16, 24, 32, 48, 64, 96]`
   - 如果 spacing scale 不完整（少於 5 個值）

3. **檢測缺失的 Grid**：
   - 如果 `breakpoints` 是預設值
   - 如果缺少 grid 配置（columns, max_width, gutter）

4. **檢測缺失的 Design System Tokens**：
   - 如果沒有 Visual Lens，缺少 radius, shadow, motion tokens

**生成 Stitch Prompt Pack 並引導用戶**：

如果檢測到缺失，**自動生成 Stitch Prompt Pack 並提供一鍵引導**：

1. **生成缺口報告**：
   ```python
   from capabilities.web_generation.services.gap_detection import detect_gaps
   from capabilities.web_generation.services.stitch_prompt_generator import generate_stitch_prompt_pack

   gap_report = detect_gaps(
       visual_lens=visual_lens,
       routed_theme=theme,
       style_schema=style_schema
   )
   ```

2. **生成 Stitch Prompt Pack**：
   ```python
   prompt_pack = generate_stitch_prompt_pack(
       gap_report=gap_report,
       visual_lens=visual_lens,
       theme=theme
   )
   ```

3. **顯示缺口卡（Gap Card）**：
   ```markdown
   ## 🎨 檢測到設計系統 tokens 缺失

   我發現您的樣式配置中有一些字段使用了預設值，可能無法完全反映您想要的設計風格。

   **缺失的字段**：
   - Typography（字體配置）：{gap_report.missing_typography}
   - Spacing（間距尺度）：{gap_report.missing_spacing}
   - Grid（版面系統）：{gap_report.missing_grid}
   - Design System Tokens：{gap_report.missing_design_tokens}

   **建議**：使用 Stitch 設計工具來補充這些缺失的設計細節。

   ### 一鍵引導流程：

   1. **點擊「打開 Stitch」按鈕** → 新分頁打開 [stitch.withgoogle.com](https://stitch.withgoogle.com)

   2. **複製 Prompt #1** → 貼到 Stitch 中，建立基礎版型與字體系統

   3. **完成後，複製 Prompt #2** → 套用色彩系統與間距尺度

   4. **完成後，複製 Prompt #3** → 設計元件與設計系統 tokens

   5. **（可選）複製 Prompt #4** → 精修設計細節

   6. **在 Stitch 中導出前端碼**：
      - 點擊「Export」→ 選擇「Export front-end code」
      - 或「Paste to Figma」（如果需要）

   7. **拖回系統**：
      - 貼上 HTML/CSS 內容
      - 或上傳 zip 檔案
      - 系統會自動提取設計 tokens 並回寫到 Theme Library

   **或者**：我可以繼續使用預設值生成樣式系統，您後續可以手動調整。
   ```

4. **顯示 Stitch Prompt Pack**：
   ```markdown
   ### Stitch Prompt Pack（{prompt_pack.total_steps} 步驟）

   **步驟 1：建立基礎版型與字體系統**
   ```
   {prompt_pack.prompts[0].prompt}
   ```
   [📋 複製 Prompt #1]

   **步驟 2：套用色彩系統與間距尺度**
   ```
   {prompt_pack.prompts[1].prompt}
   ```
   [📋 複製 Prompt #2]

   **步驟 3：設計元件與設計系統 tokens**
   ```
   {prompt_pack.prompts[2].prompt}
   ```
   [📋 複製 Prompt #3]

   {如果有步驟 4，顯示步驟 4}
   ```

**決策卡：是否使用 Stitch 補充**：

```decision_card
card_id: dc_use_stitch_to_fill_gaps
type: selection
title: "檢測到設計 tokens 缺失"
question: "是否要使用 Stitch 來補充缺失的設計細節？"
options:
  - value: "yes"
    label: "是，使用 Stitch 補充"
    description: "執行 design_snapshot_ingestion playbook，匯入 Stitch 設計"
    action: "引導用戶執行 design_snapshot_ingestion playbook"
  - value: "no"
    label: "否，繼續使用預設值"
    description: "使用預設值生成樣式系統，後續可手動調整"
    action: "繼續執行，記錄使用的預設值"
  - value: "later"
    label: "稍後再處理"
    description: "先生成基本樣式系統，稍後再補充"
    action: "繼續執行，記錄缺失的字段"
```

**如果用戶選擇「是，使用 Stitch 補充」**：

1. **提供一鍵引導**：
   - 顯示「打開 Stitch」按鈕（連結到 https://stitch.withgoogle.com）
   - 顯示所有 Stitch Prompts（可複製）
   - 引導用戶逐步完成設計

2. **等待用戶完成並匯入**：
   - 引導用戶執行 `design_snapshot_ingestion` playbook
   - 或直接在 UI 中上傳 HTML/CSS/zip
   - 系統自動執行：
     - Theme Fingerprint Extraction（從 HTML/CSS 提取 tokens）
     - 回寫到 Theme Library（更新或新增 theme）
     - 更新 `final_theme_config`

3. **自動重新檢測**：
   - 檢查是否有新的 Design Snapshot artifact
   - 如果有，從 Design Snapshot 提取缺失的 tokens
   - 自動更新 Theme Library
   - 更新 `final_theme_config`
   - 提示用戶「已自動補充缺失的 tokens，可以重新生成樣式系統」

**如果用戶選擇「否，繼續使用預設值」**：

- 繼續執行，使用預設值
- 記錄缺失的字段，供後續參考

**輸出**：
- `missing_tokens`: 缺失的 tokens 列表
- `use_stitch`: 是否使用 Stitch 補充（true/false）
- `final_theme_config`: 最終的 ThemeConfig（可能包含從 Design Snapshot 補充的 tokens）

#### 步驟 1.6: 最終驗證 Theme 配置

確保最終的 `theme_config` 包含所有必需的字段：
- ✅ `colors`: primary, secondary, accent, neutral, semantic
- ✅ `typography`: heading_font, body_font, type_scale, line_heights
- ✅ `spacing`: spacing scale array
- ✅ `breakpoints`: sm, md, lg, xl

**輸出**：
- `final_theme_config`: 最終的 ThemeConfig（用於生成樣式文件）
- `theme_source`: 配置來源記錄（Visual Lens + Theme / Design Snapshot / Brand Context / site_spec / 預設值）
- `missing_tokens_log`: 缺失的 tokens 記錄（如果使用預設值）

### Phase 2: 生成 CSS 變量文件

#### 步驟 2.0: 應用 Theme 的設計系統 Tokens（如果存在 Visual Lens）

**如果 `has_visual_lens = true` 且使用了 Token Synthesis**：

使用 Theme 的完整設計系統 tokens（已經在 `final_theme_config` 中）：

1. **邊框半徑**：
   - 從 Theme 的 `radius` tokens 取得：`theme.radius.sm`, `theme.radius.md`, `theme.radius.lg`
   - 設定 CSS 變量：
     - `--border-radius-sm: {theme.radius.sm}px`
     - `--border-radius-md: {theme.radius.md}px`
     - `--border-radius-lg: {theme.radius.lg}px`

2. **陰影樣式**：
   - 從 Theme 的 `shadow` tokens 取得：`theme.shadow.sm`, `theme.shadow.md`, `theme.shadow.lg`
   - 設定 CSS 變量：
     - `--shadow-sm: {theme.shadow.sm}`
     - `--shadow-md: {theme.shadow.md}`
     - `--shadow-lg: {theme.shadow.lg}`

3. **動畫節奏**：
   - 從 Theme 的 `motion` tokens 取得：`theme.motion.duration_scale`
   - 設定 CSS 變量：
     - `--transition-duration-fast: {theme.motion.duration_scale[0]}ms`
     - `--transition-duration-normal: {theme.motion.duration_scale[1]}ms`
     - `--transition-duration-slow: {theme.motion.duration_scale[2]}ms`
   - 設定 easing：`--transition-easing: {theme.motion.easing}`

4. **間距尺度**：
   - 從 Theme 的 `spacing` tokens 取得：`theme.spacing.scale`
   - 已經在 `final_theme_config.spacing` 中，直接使用

**如果沒有 Visual Lens**：

使用 Visual Lens 的 Web Translation Rules（如果存在）或預設值。

**輸出**：
- `design_system_css_vars`: 設計系統 tokens 對應的 CSS 變量

#### 步驟 2.1: 構建 CSS 變量結構
根據 `final_theme_config` 和設計系統 tokens 構建 CSS 變量：

```css
:root {
  /* Colors (from Visual Lens + Theme) */
  --color-primary: {final_theme_config.colors.primary};
  --color-secondary: {final_theme_config.colors.secondary};
  --color-accent: {final_theme_config.colors.accent};
  --color-neutral-{n}: {final_theme_config.colors.neutral[n]};
  --color-success: {final_theme_config.colors.semantic.success};
  --color-warning: {final_theme_config.colors.semantic.warning};
  --color-error: {final_theme_config.colors.semantic.error};
  --color-info: {final_theme_config.colors.semantic.info};

  /* Typography (from Theme) */
  --font-heading: {final_theme_config.typography.heading_font};
  --font-body: {final_theme_config.typography.body_font};
  --font-accent: {final_theme_config.typography.accent_font};
  --font-size-h1: {final_theme_config.typography.type_scale.h1};
  --font-size-h2: {final_theme_config.typography.type_scale.h2};
  --font-size-h3: {final_theme_config.typography.type_scale.h3};
  --font-size-body: {final_theme_config.typography.type_scale.body};
  --line-height-h1: {final_theme_config.typography.line_heights.h1};
  --line-height-h2: {final_theme_config.typography.line_heights.h2};
  --line-height-body: {final_theme_config.typography.line_heights.body};

  /* Spacing (from Theme) */
  --spacing-{n}: {final_theme_config.spacing[n]}px;

  /* Breakpoints (from Theme) */
  --breakpoint-sm: {final_theme_config.breakpoints.sm};
  --breakpoint-md: {final_theme_config.breakpoints.md};
  --breakpoint-lg: {final_theme_config.breakpoints.lg};
  --breakpoint-xl: {final_theme_config.breakpoints.xl};

  /* Design System Tokens (from Theme) */
  {design_system_css_vars}
}
```

#### 步驟 2.2: 生成 variables.css
**必須**使用 `filesystem_write_file` 工具保存 CSS 變量文件：

- **文件路徑**：`styles/variables.css`（在 Project Sandbox 中）
- **完整路徑**：`sandboxes/{workspace_id}/{project_type}/{project_id}/styles/variables.css`

### Phase 3: 生成 Tailwind 配置文件

#### 步驟 3.1: 構建 Tailwind 配置結構
根據 `final_theme_config` 構建 Tailwind 配置：

```javascript
/** @type {import('tailwindcss').Config} */
module.exports = {
  content: [
    "./app/**/*.{js,ts,jsx,tsx,mdx}",
    "./pages/**/*.{js,ts,jsx,tsx,mdx}",
    "./components/**/*.{js,ts,jsx,tsx,mdx}",
    "./sections/**/*.{js,ts,jsx,tsx,mdx}",
  ],
  theme: {
    extend: {
      colors: {
        primary: '{final_theme_config.colors.primary}',
        secondary: '{final_theme_config.colors.secondary}',
        accent: '{final_theme_config.colors.accent}',
        neutral: {
          // 根據 final_theme_config.colors.neutral 生成
          // 例如：50: '{final_theme_config.colors.neutral[0]}', 100: '{final_theme_config.colors.neutral[1]}', ...
        },
        success: '{final_theme_config.colors.semantic.success}',
        warning: '{final_theme_config.colors.semantic.warning}',
        error: '{final_theme_config.colors.semantic.error}',
        info: '{final_theme_config.colors.semantic.info}',
      },
      fontFamily: {
        heading: ['{final_theme_config.typography.heading_font}', 'sans-serif'],
        body: ['{final_theme_config.typography.body_font}', 'sans-serif'],
        accent: ['{final_theme_config.typography.accent_font}', 'serif'],
      },
      fontSize: {
        h1: '{final_theme_config.typography.type_scale.h1}',
        h2: '{final_theme_config.typography.type_scale.h2}',
        h3: '{final_theme_config.typography.type_scale.h3}',
        body: '{final_theme_config.typography.type_scale.body}',
      },
      lineHeight: {
        h1: {final_theme_config.typography.line_heights.h1},
        h2: {final_theme_config.typography.line_heights.h2},
        body: {final_theme_config.typography.line_heights.body},
      },
      spacing: {
        // 根據 final_theme_config.spacing 生成
        // 例如：1: '{final_theme_config.spacing[0]}px', 2: '{final_theme_config.spacing[1]}px', ...
      },
      borderRadius: {
        sm: '{theme.radius.sm}px',  // 如果存在 Visual Lens + Theme
        md: '{theme.radius.md}px',
        lg: '{theme.radius.lg}px',
      },
      boxShadow: {
        sm: '{theme.shadow.sm}',  // 如果存在 Visual Lens + Theme
        md: '{theme.shadow.md}',
        lg: '{theme.shadow.lg}',
      },
      transitionDuration: {
        fast: '{theme.motion.duration_scale[0]}ms',  // 如果存在 Visual Lens + Theme
        normal: '{theme.motion.duration_scale[1]}ms',
        slow: '{theme.motion.duration_scale[2]}ms',
      },
      transitionTimingFunction: {
        default: '{theme.motion.easing}',  // 如果存在 Visual Lens + Theme
      },
      screens: {
        sm: '{final_theme_config.breakpoints.sm}',
        md: '{final_theme_config.breakpoints.md}',
        lg: '{final_theme_config.breakpoints.lg}',
        xl: '{final_theme_config.breakpoints.xl}',
      },
    },
  },
  plugins: [],
}
```

#### 步驟 3.2: 生成 tailwind.config.js
**必須**使用 `filesystem_write_file` 工具保存 Tailwind 配置文件：

- **文件路徑**：`tailwind.config.js`（在 Project Sandbox 根目錄）
- **完整路徑**：`sandboxes/{workspace_id}/{project_type}/{project_id}/tailwind.config.js`

### Phase 4: 生成全局樣式文件

#### 步驟 4.0: 應用 Style Guardrails（如果存在 Visual Lens）

如果 `has_visual_lens = true`，應用 Visual Lens 的 Style Guardrails：

1. **避免禁止元素**：
   - 檢查 `visual_lens.style_guardrails.forbidden_elements`
   - 在全局樣式中避免使用這些元素
   - 例如：如果 `forbidden_elements` 包含 "gradient"，則不使用漸變背景

2. **確保必需元素**：
   - 檢查 `visual_lens.style_guardrails.required_elements`
   - 在全局樣式中確保包含這些元素
   - 例如：如果 `required_elements` 包含 "whitespace"，則確保有足夠的留白

**輸出**：
- `guardrails_applied`: Style Guardrails 應用結果

#### 步驟 4.1: 構建全局樣式結構
根據 theme 配置和 Visual Lens 規則構建全局樣式：

```css
@import './variables.css';
@tailwind base;
@tailwind components;
@tailwind utilities;

@layer base {
  * {
    @apply box-border;
  }

  html {
    @apply scroll-smooth;
  }

  body {
    @apply font-body text-body antialiased;
    font-family: var(--font-body);
    font-size: var(--font-size-body);
    line-height: var(--line-height-body);
    color: var(--color-neutral-900);
    background-color: var(--color-neutral-50);
  }

  h1, h2, h3, h4, h5, h6 {
    @apply font-heading font-bold;
    font-family: var(--font-heading);
  }

  h1 {
    font-size: var(--font-size-h1);
    line-height: var(--line-height-h1);
  }

  h2 {
    font-size: var(--font-size-h2);
    line-height: var(--line-height-h2);
  }

  h3 {
    font-size: var(--font-size-h3);
    line-height: var(--line-height-h3);
  }

  a {
    @apply text-primary hover:text-accent transition-colors;
  }

  button {
    @apply transition-all;
  }
}

@layer components {
  .container-custom {
    @apply mx-auto px-4;
    max-width: 1200px;
  }

  .section-padding {
    @apply py-16 md:py-24;
  }
}

@layer utilities {
  .text-balance {
    text-wrap: balance;
  }
}
```

#### 步驟 4.2: 生成 global.css
**必須**使用 `filesystem_write_file` 工具保存全局樣式文件：

- **文件路徑**：`styles/global.css`（在 Project Sandbox 中）
- **完整路徑**：`sandboxes/{workspace_id}/{project_type}/{project_id}/styles/global.css`

### Phase 5: 生成樣式說明文檔（可選）

#### 步驟 5.1: 生成樣式使用指南
**可選**生成樣式使用說明文檔：

- **文件路徑**：`styles/README.md`
- **內容**：
  - 色彩系統說明
  - 字體系統說明
  - 間距系統說明
  - 響應式斷點說明
  - 使用範例

### Phase 6: 驗證生成的樣式文件

#### 步驟 6.1: 驗證 CSS 語法
- 檢查 CSS 變量文件語法是否正確
- 檢查全局樣式文件語法是否正確

#### 步驟 6.2: 驗證 Tailwind 配置
- 檢查 Tailwind 配置格式是否正確
- 確保所有顏色、字體、間距都已正確映射

#### 步驟 6.3: 檢查文件完整性
- 確認所有必需的文件都已生成
- 確認文件路徑正確

### Phase 7: 註冊 Artifacts

#### 步驟 7.1: 註冊樣式文件 Artifacts
**必須**使用 `artifact_registry.register_artifact` 註冊產出的 artifacts：

1. **CSS 變量文件**：
   - **artifact_id**：`style_variables`
   - **artifact_type**：`css`
   - **path**：`styles/variables.css`

2. **Tailwind 配置**：
   - **artifact_id**：`tailwind_config`
   - **artifact_type**：`config`
   - **path**：`tailwind.config.js`

3. **全局樣式**：
   - **artifact_id**：`global_styles`
   - **artifact_type**：`css`
   - **path**：`styles/global.css`

### Phase 8: 執行記錄保存

#### 步驟 8.1: 保存對話歷史
**必須**使用 `filesystem_write_file` 工具保存完整的對話歷史：

- 文件路徑: `artifacts/style_system_gen/{{execution_id}}/conversation_history.json`
- 內容: 完整的對話歷史（包含所有 user 和 assistant 消息）
- 格式: JSON 格式，包含時間戳和角色信息

#### 步驟 8.2: 保存執行摘要
**必須**使用 `filesystem_write_file` 工具保存執行摘要：

- 文件路徑: `artifacts/style_system_gen/{{execution_id}}/execution_summary.md`
- 內容:
  - 執行時間
  - 執行 ID
  - Playbook 名稱
  - 讀取的 site_spec.yaml 路徑
  - 生成的樣式文件列表
  - 使用的預設值（如有）
  - 驗證結果

## 個人化

基於使用者的 Mindscape 個人檔案：
- **技術等級**：若為「進階」，包含更多自訂選項和進階配置
- **詳細程度**：若偏好「高」，提供更詳細的樣式說明和註釋
- **工作風格**：若偏好「結構化」，提供更清晰的樣式組織結構

## 與長期意圖的整合

若使用者有相關的活躍意圖（例如「建立品牌網站」），明確引用：
> "由於您正在進行「建立品牌網站」，我將根據您的品牌識別生成一致的樣式系統..."

## 成功標準

- CSS 變量文件已生成到 `styles/variables.css`
- Tailwind 配置文件已生成到 `tailwind.config.js`
- 全局樣式文件已生成到 `styles/global.css`
- 所有樣式文件語法正確
- 所有 theme 配置都已正確映射到樣式系統
- Artifacts 已正確註冊
- 樣式系統可以與後續組件生成和頁面組裝無縫整合

## 注意事項

- **Project Context**：必須在 web_page 或 website project 的 context 中執行
- **依賴關係**：必須先執行 `site_spec_generation` playbook
- **Sandbox 路徑**：確保使用 Project Sandbox 路徑，而非 artifacts 路徑
- **向後兼容**：如果沒有 project context，可以降級到 artifacts 路徑（但會提示用戶）
- **預設值處理**：如果 theme 配置不完整，使用合理的預設值並記錄

## 相關文檔

- **Schema 定義**：`capabilities/web_generation/schema/site_spec_schema.py`
- **Theme Library**：`capabilities/web_generation/schema/theme_library.py`
- **Theme Routing**：`capabilities/web_generation/services/theme_routing.py`
- **Token Synthesis**：`capabilities/web_generation/services/token_synthesis.py`
- **網站規格生成**：`capabilities/web_generation/playbooks/zh-TW/site_spec_generation.md`
- **完整網站生成流程**：`capabilities/web_generation/docs/complete-pipeline-workflow.md`
- **Theme Library 實現總結**：`docs-internal/implementation/2025-12-19/unsplash-visual-lens-e2e-testing/theme-library-implementation-2025-12-20.md`

