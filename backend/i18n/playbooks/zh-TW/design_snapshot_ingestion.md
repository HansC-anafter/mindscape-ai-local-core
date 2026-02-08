---
playbook_code: design_snapshot_ingestion
version: 1.0.0
capability_code: web_generation
name: 設計快照匯入
description: |
  匯入 Stitch 或其他設計工具的產出，建立版本化的設計快照 artifact。
  作為 web-generation 流程的「上游輸入基準線」，提供可視化的設計參考。
tags:
  - web
  - design
  - snapshot
  - ingestion
  - governance

kind: user_workflow
interaction_mode:
  - conversational
  - needs_review
visible_in:
  - workspace_tools_panel
  - workspace_playbook_menu

execution_profile: short_flow  # 短流程 playbook，不需要 LangGraph

required_tools:
  # 基礎 Artifact 操作
  - artifact.create
  - artifact.list
  - artifact.read

  # 檔案系統操作
  - filesystem_write_file
  - filesystem_read_file
  - filesystem_list
  - filesystem_mkdir

  # Sandbox 文件上傳（新增）
  - upload_file_to_sandbox
  - upload_design_files_to_sandbox

language_strategy: model_native
locale: zh-TW
supported_locales:
  - zh-TW
  - en
default_locale: zh-TW
auto_localize: true

entry_agent_type: planner
icon: 🎨
---

# 設計快照匯入 - SOP

## 目標

匯入外部設計工具（如 Google Labs Stitch、Figma）的產出，建立版本化的 Design Snapshot Artifact。此快照將作為後續 web-generation 流程的「上游輸入基準線」，降低 prompt 漂移並加快設計收斂。

**工作流程說明**：
- 這是完整網站生成流程的 **Phase 0**：設計探索與匯入
- 支援多種來源：Stitch HTML/CSS、Figma（未來擴展）、手動上傳
- 建立可版本化、可追溯的設計快照 artifact

---

## 執行步驟

### Phase 0: 檢查 Project Context

#### 步驟 0.1: 檢查是否有活躍的 web_page 或 website project
- 檢查 execution context 中是否有 `project_id`
- 如果有，確認 project type 為 `web_page` 或 `website`
- 如果沒有，提示用戶需要先創建 project（但 playbook 仍可執行，建立 workspace 級別的 snapshot）

#### 步驟 0.2: 獲取 Project Sandbox 路徑（如果有的話）
- 使用 `project_sandbox_manager.get_sandbox_path()` 獲取 sandbox 路徑
- Sandbox 路徑結構：`sandboxes/{workspace_id}/{project_type}/{project_id}/`
- 確保 `design_snapshots/` 目錄存在（用於儲存原始檔案）

**⚠️ 用戶手動準備文件（選項 C）**：
如果用戶選擇「提供檔案路徑」，需要先將 Stitch 導出的 HTML/CSS 文件放入 sandbox：
1. 從 Stitch 導出 HTML/CSS 文件
2. 使用 filesystem 工具或 UI 將文件上傳到 sandbox：
   - 建議路徑：`design_snapshots/stitch_export/`（臨時目錄）
   - 或直接放在 sandbox 根目錄
3. 記錄文件路徑，供後續步驟使用

#### 步驟 0.3: 檢查是否有父版本 Snapshot
- 使用 `artifact.list` 查詢 `kind: design_snapshot`
- 如果有多個 snapshots，詢問用戶是否要基於某個 snapshot 創建新版本
- 記錄 `parent_snapshot_id`（如果選擇）

---

### Phase 1: 匯入來源選擇

#### 步驟 1.1: 選擇匯入來源

詢問用戶選擇匯入來源：

**選項 A：上傳 HTML/CSS 檔案** ✅ **已實作**
- 使用 `upload_file_to_sandbox` 或 `upload_design_files_to_sandbox` 工具上傳檔案
- 檔案會自動寫入到 project sandbox 的 `design_snapshots/stitch_export/` 目錄
- 支援 base64 data URL 格式或純文字內容
- 上傳後自動讀取檔案內容進行處理

**使用方式**：
```tool
upload_design_files_to_sandbox
workspace_id: {workspace_id}
project_id: {project_id}
html_content: {html_content}  # base64 data URL 或純文字
css_content: {css_content}    # base64 data URL 或純文字
html_file_name: "stitch_export.html"
css_file_name: "stitch_export.css"
target_directory: "design_snapshots/stitch_export"
```

**或單獨上傳**：
```tool
upload_file_to_sandbox
workspace_id: {workspace_id}
project_id: {project_id}
file_content: {file_content}  # base64 data URL 或純文字
file_name: "stitch_export.html"
target_path: "design_snapshots/stitch_export/stitch_export.html"
```

**選項 B：貼上 HTML/CSS 內容**
- 要求用戶貼上 HTML 和 CSS 內容
- 分別儲存為字符串

**選項 C：提供檔案路徑**（如果在 sandbox 中已有檔案）
- 讀取 sandbox 中的檔案
- **⚠️ 前置步驟**：用戶需要先將 Stitch 導出的 HTML/CSS 文件放入 sandbox
  - 方法 1：使用 filesystem 工具手動上傳
  - 方法 2：透過 UI 上傳文件到 sandbox
  - 建議路徑：`design_snapshots/stitch_export/` 或 sandbox 根目錄
  - 文件命名：`stitch_export.html` 和 `stitch_export.css`（或用戶自訂）

**選項 D：Figma URL**（未來擴展）
- 目前提示「尚未支援，請先匯出為 HTML/CSS」

**決策卡：匯入來源**

```decision_card
card_id: dc_import_source
type: selection
title: "選擇匯入來源"
question: "請選擇設計快照的來源"
options:
  - "上傳 HTML/CSS 檔案"
  - "貼上 HTML/CSS 內容"
  - "提供檔案路徑"
description: "目前支援 HTML/CSS 匯入，Figma 整合將在未來版本推出"
```

---

### Phase 2: 安全檢查與 Sanitization ⚠️ 安全邊界

#### 步驟 2.1: HTML 安全處理

**⚠️ 核心安全原則：不執行、不注入**

1. **移除危險標籤**：
   - 移除所有 `<script>` 標籤及其內容
   - 移除 `<iframe>`, `<object>`, `<embed>`
   - 移除 `<form>`, `<input>`, `<button>`（互動表單元素）

2. **移除危險屬性**：
   - 移除所有 inline event handlers：`onclick`, `onerror`, `onload`, `onmouseover` 等
   - 移除 `javascript:` URLs

3. **計算 source_hash**（用於可重現性）：
   ```python
   import hashlib
   source_hash = hashlib.sha256(html_content.encode()).hexdigest()
   ```

4. **儲存策略**：
   - **原始檔案**（安全處理後）：儲存到 `design_snapshots/{version}/original.html`
   - **Metadata**：儲存在 artifact 的 metadata 欄位（不包含可執行程式碼）

#### 步驟 3.2: CSS 安全處理

1. **移除危險規則**：
   - 移除 `@import`（可能載入外部資源）
   - 移除外部 `url()`（但保留 data: URLs）
   - 移除 `expression()`（IE 的 JavaScript 執行）
   - 移除 `javascript:` URLs

2. **儲存**：
   - 安全處理後的 CSS 儲存到 `design_snapshots/{version}/styles.css`

---

### Phase 4: 設計快照解析

#### 步驟 4.1: HTML 結構解析

使用 HTML 解析器（如 BeautifulSoup）提取：

1. **Navigation 結構**：
   - `<nav>` 標籤及其子元素
   - 導航項目（label、href/route）
   - 導航層級（top/sidebar/footer）

2. **頁面狀態**：
   - CSS classes 中包含 `hover`, `active`, `disabled` 等狀態標記
   - 互動元素的狀態變化

3. **組件結構**：
   - 主要 section（hero、about、features 等）
   - 組件層級結構

**記錄解析品質**：
- 如果導航結構清晰 → `extraction_quality: "high"`
- 如果部分資訊無法判定 → `extraction_quality: "medium"`, 記錄 `missing_fields`
- 如果大量缺失 → `extraction_quality: "low"`

#### 步驟 4.2: CSS 樣式提取

提取樣式資訊：

1. **Color Palette**：
   - CSS variables（`--color-primary` 等）
   - 硬編碼顏色值（`#ff0000`, `rgb()` 等）
   - 識別主要色彩、次要色彩、強調色

2. **Typography**：
   - `font-family` 定義
   - `font-size` scale（h1, h2, h3, body 等）
   - `line-height` 設定
   - `font-weight` 變化

3. **Spacing**：
   - `margin` / `padding` 值
   - 識別 spacing scale（如 4, 8, 12, 16, 24, 32...）

4. **其他設計 tokens**：
   - `border-radius`
   - `box-shadow`
   - `breakpoints`（如果使用 media queries）

**記錄缺失欄位**：
- 如果無法識別 breakpoints → `missing_fields: ["breakpoints"]`
- 如果無法識別 state tokens → `missing_fields: ["state_tokens"]`

#### 步驟 4.3: 設計假設提取

基於解析結果，記錄設計假設：

1. **Navigation 假設**：
   - 導航結構的假設（如果解析不完整）
   - 導航行為假設

2. **狀態假設**：
   - 互動狀態的假設（hover、active 等）

3. **響應式假設**：
   - 如果無法識別 breakpoints，記錄假設（如「假設使用 mobile-first」）

---

### Phase 5: 版本鏈與 Metadata 設定

#### 步驟 5.1: 版本資訊

詢問或自動生成：

- **版本號**：如果是第一個 snapshot，使用 `1.0.0`；如果有父版本，建議 bump minor
- **Variant ID**：如果有多個 UI variants，記錄 `variant_id`（如 `variant_a`, `variant_b`）
- **來源工具**：`source_tool: "stitch" | "figma" | "manual"`

#### 步驟 5.2: 版本鏈設定（可選）

詢問用戶：

**決策卡：版本鏈設定**

```decision_card
card_id: dc_version_chain
type: optional
title: "版本鏈設定"
question: "此 snapshot 是否有父版本或屬於某個分支？"
options:
  - parent_snapshot_id: "選擇父版本（可選）"
  - branch: "分支名稱（如 'main', 'experiment-a'）"
  - lineage_key: "版本線索鍵（如 'exploration_001'）"
allow_custom: true
```

#### 步驟 5.3: Baseline 綁定（可選）

詢問用戶是否要立即設為 baseline：

**決策卡：Baseline 綁定**

```decision_card
card_id: dc_baseline_binding
type: optional
title: "Baseline 綁定"
question: "是否要將此 snapshot 設為 baseline？"
options:
  - baseline_for: "Project ID（可選，None = workspace 級別）"
  - lock_mode: "鎖定模式（'locked' 或 'advisory'）"
```

**說明**：
- 如果不在此階段設定，後續可以在 UI 中設定
- `lock_mode: "locked"` = 硬約束（後續 playbook 必須遵循）
- `lock_mode: "advisory"` = 參考建議（後續 playbook 可參考但不強制）

---

### Phase 6: 創建 Design Snapshot Artifact

#### 步驟 6.1: 準備 Metadata

使用 `DesignSnapshotMetadata` schema 準備 metadata：

```python
from capabilities.web_generation.schema import DesignSnapshotMetadata
from datetime import datetime

metadata = DesignSnapshotMetadata(
    # 基礎識別
    kind="design_snapshot",
    source_tool="stitch",  # 從用戶選擇取得
    version="1.0.0",  # 從版本資訊取得
    snapshot_date=datetime.utcnow(),

    # 基準線鎖定機制（如果用戶選擇設定）
    variant_id="variant_a",  # 如果有 variants
    active_variant="variant_a",  # 當前活躍的 variant
    baseline_for="project_123",  # 如果設為 baseline
    lock_mode="advisory",  # 如果設為 baseline

    # 可重現性
    source_hash=source_hash,  # Phase 2 計算的
    extractor_version="1.0.0",  # 解析器版本
    transformer_version=None,  # 尚未轉換

    # 版本鏈
    parent_snapshot_id="<parent_id>",  # 如果選擇父版本
    branch="main",  # 如果指定分支
    lineage_key="exploration_001",  # 如果指定

    # UI 結構（從 Phase 3 解析結果）
    navigation_structure={
        "top": [...],
        "sidebar": [...],
        "footer": [...]
    },
    page_states=["default", "hover", "active"],

    # 樣式提取（從 Phase 3 解析結果）
    extracted_colors={
        "primary": "#ff0000",
        "secondary": "#00ff00",
        ...
    },
    extracted_typography={
        "heading_font": "Arial",
        "body_font": "Arial",
        "type_scale": {...}
    },
    extracted_spacing=[4, 8, 12, 16, 24, 32],

    # 置信度與缺失標記
    extraction_quality="high",  # "low" | "medium" | "high"
    missing_fields=["breakpoints"],  # 如果無法解析
    assumptions=[
        "Responsive design assumes mobile-first",
        "Navigation structure inferred from HTML classes"
    ],
    design_assumptions={
        "navigation": {...},
        "states": {...},
        "breakpoints": {...}
    }
)
```

#### 步驟 6.2: 儲存原始檔案到 Sandbox

如果 project_id 存在：

```tool
filesystem_mkdir
path: design_snapshots/{version}/
```

```tool
filesystem_write_file
path: design_snapshots/{version}/original.html
content: {安全處理後的 HTML}
```

```tool
filesystem_write_file
path: design_snapshots/{version}/styles.css
content: {安全處理後的 CSS}
```

#### 步驟 6.3: 創建 Artifact

```tool
create_artifact
workspace_id: {workspace_id}
playbook_code: design_snapshot_ingestion
artifact_type: markdown
title: "Design Snapshot v{version} - {source_tool}"
summary: "設計快照：來源 {source_tool}，版本 {version}，品質 {extraction_quality}"
content:
  # Design Snapshot Summary

  **來源**：{source_tool}
  **版本**：{version}
  **建立時間**：{snapshot_date}

  ## 解析品質
  - 品質等級：{extraction_quality}
  - 缺失欄位：{missing_fields}

  ## 設計要素
  - 導航結構：{已解析/部分解析}
  - 色彩方案：{已提取}
  - 字體系統：{已提取}

  ## 設計假設
  {assumptions 列表}
metadata:
  # 使用 DesignSnapshotMetadata schema
  kind: design_snapshot
  source_tool: {source_tool}
  version: {version}
  snapshot_date: {ISO8601}
  variant_id: {variant_id}
  active_variant: {active_variant}
  source_hash: {source_hash}
  extractor_version: {extractor_version}
  parent_snapshot_id: {parent_snapshot_id}
  branch: {branch}
  lineage_key: {lineage_key}
  navigation_structure: {...}
  page_states: [...]
  extracted_colors: {...}
  extracted_typography: {...}
  extracted_spacing: [...]
  extraction_quality: {extraction_quality}
  missing_fields: [...]
  assumptions: [...]
  design_assumptions: {...}
primary_action_type: view
```

---

### Phase 7: 可選的 Baseline 設定

如果用戶在 Phase 4.3 選擇設為 baseline，執行：

```tool
# 透過 API 設定 baseline（需要實現 tool 或直接調用）
# POST /api/v1/workspaces/{workspace_id}/web-generation/baseline
# Body: {
#   "snapshot_id": "{artifact_id}",
#   "variant_id": "{variant_id}",
#   "project_id": "{project_id}",
#   "lock_mode": "{lock_mode}"
# }
```

**注意**：如果 tool 尚未實現，可以提示用戶「請在 UI 中設定 baseline」。

---

### Phase 8: 自動提取並回寫 Theme Library（新增）

#### 步驟 8.1: 執行 Theme Fingerprint Extraction

**從 Design Snapshot 的 CSS 提取設計 tokens**：

```python
from capabilities.web_generation.tools.theme_fingerprint_tools import (
    extract_tokens_from_css,
    normalize_tokens
)

# 讀取 CSS 內容（從 Phase 3 解析結果或從 sandbox 讀取）
css_content = {安全處理後的 CSS}

# 提取 tokens
raw_tokens = extract_tokens_from_css(css_content)

# 標準化 tokens
normalized_tokens = normalize_tokens(raw_tokens)
```

**提取的 tokens**：
- Typography（font-family, font-size, line-height）
- Colors（CSS variables, color values）
- Spacing（spacing scale）
- Radius（border-radius values）
- Shadow（box-shadow values）
- Breakpoints（media query breakpoints）

#### 步驟 8.2: 檢查是否需要回寫 Theme Library

**判斷條件**：
1. **如果從 Stitch 匯入**（`source_tool = "stitch"`）：
   - 檢查是否有 Visual Lens 或 routed theme
   - 如果有，檢查提取的 tokens 是否補充了缺失的部分
   - 如果補充了缺失的 tokens，執行回寫

2. **如果提取的 tokens 品質高**（`extraction_quality = "high"`）：
   - 檢查是否可以用來更新現有的 theme
   - 或創建新的 theme archetype

**決策邏輯**：
```python
# 檢查是否需要回寫
should_write_back = False
write_back_reason = None

if source_tool == "stitch":
    # 從 gap_report 檢查（如果存在）
    if gap_report and gap_report.has_gaps:
        # 檢查提取的 tokens 是否補充了缺失的部分
        if normalized_tokens.get("typography") and "typography" in gap_report.missing_typography:
            should_write_back = True
            write_back_reason = "補充缺失的 Typography tokens"
        if normalized_tokens.get("spacing_scale") and gap_report.missing_spacing:
            should_write_back = True
            write_back_reason = "補充缺失的 Spacing tokens"
        if normalized_tokens.get("radius_scale") and "radius" in gap_report.missing_design_tokens:
            should_write_back = True
            write_back_reason = "補充缺失的 Design System tokens"

if extraction_quality == "high" and not should_write_back:
    # 檢查是否可以用來更新或創建 theme
    if normalized_tokens.get("typography") and normalized_tokens.get("spacing_scale"):
        should_write_back = True
        write_back_reason = "高品質 tokens，可用於更新 Theme Library"
```

#### 步驟 8.3: 回寫到 Theme Library

**如果 `should_write_back = true`**：

**使用 Theme Library Writer 服務**：

```python
from capabilities.web_generation.services.theme_library_writer import write_tokens_to_theme_library

# 回寫 tokens 到 Theme Library
write_result = write_tokens_to_theme_library(
    normalized_tokens=normalized_tokens,
    gap_report=gap_report,  # 如果存在
    routed_theme_id=routed_theme_id,  # 如果存在
    source_tool=source_tool,
    extraction_quality=extraction_quality
)

# 檢查回寫結果
if write_result.success:
    if write_result.updated_theme_id:
        logger.info(f"已更新 theme: {write_result.updated_theme_id}")
        logger.info(f"更新的字段: {write_result.updated_fields}")
    if write_result.new_theme_id:
        logger.info(f"已創建新 theme: {write_result.new_theme_id}")
else:
    logger.warning(f"未執行回寫: {write_result.reason}")
```

**選項 A：更新現有的 Theme**（如果有 routed_theme）：

```python
from capabilities.web_generation.schema.theme_library import BaseTheme, THEME_LIBRARY

# 取得現有的 theme
existing_theme = THEME_LIBRARY.get(routed_theme_id)

# 更新 theme 的 tokens
if normalized_tokens.get("typography"):
    # 更新 typography
    existing_theme.typography.heading_font = normalized_tokens["typography"].get("heading_font") or existing_theme.typography.heading_font
    existing_theme.typography.body_font = normalized_tokens["typography"].get("body_font") or existing_theme.typography.body_font
    if normalized_tokens["typography"].get("type_scale"):
        existing_theme.typography.type_scale.update(normalized_tokens["typography"]["type_scale"])

if normalized_tokens.get("spacing_scale"):
    existing_theme.spacing.scale = normalized_tokens["spacing_scale"]

if normalized_tokens.get("radius_scale"):
    existing_theme.radius.sm = normalized_tokens["radius_scale"].get("sm", existing_theme.radius.sm)
    existing_theme.radius.md = normalized_tokens["radius_scale"].get("md", existing_theme.radius.md)
    existing_theme.radius.lg = normalized_tokens["radius_scale"].get("lg", existing_theme.radius.lg)

# 注意：這裡只是更新內存中的 theme，實際的持久化需要通過數據庫或配置文件
# 在生產環境中，應該將更新寫入數據庫或配置文件
```

**選項 B：創建新的 Theme Archetype**（如果提取的 tokens 品質高且與現有 themes 差異大）：

```python
# 分析提取的 tokens，判斷是否應該創建新的 theme archetype
# 例如：如果 typography 是 serif + sans 組合，且 spacing 很大，可能是 "editorial_long_form" theme

new_theme_id = None
if normalized_tokens.get("typography"):
    heading_font = normalized_tokens["typography"].get("heading_font", "")
    if "serif" in heading_font.lower() or "georgia" in heading_font.lower():
        # 可能是 editorial theme
        if "editorial_long_form" not in THEME_LIBRARY:
            new_theme_id = "editorial_long_form"
            # 創建新的 theme（需要實現創建邏輯）
```

**記錄回寫結果**：

```python
write_back_result = {
    "should_write_back": should_write_back,
    "write_back_reason": write_back_reason,
    "updated_theme_id": routed_theme_id if should_write_back else None,
    "new_theme_id": new_theme_id,
    "extracted_tokens": normalized_tokens,
    "timestamp": datetime.utcnow().isoformat()
}
```

#### 步驟 8.4: 通知用戶回寫結果

**如果成功回寫**：

```markdown
## ✅ 已自動回寫 Theme Library

我已從 Stitch 設計中提取了設計 tokens 並回寫到 Theme Library：

**回寫的內容**：
- Typography tokens：{更新的字段}
- Spacing scale：{更新的值}
- Design System tokens：{更新的字段}

**更新的 Theme**：{theme_id}

現在這些 tokens 已經可以被 Theme Routing 使用，您可以重新執行 `style_system_gen` playbook 來生成完整的樣式系統。
```

**如果未回寫**：

```markdown
## ℹ️ 未執行回寫

提取的 tokens 品質：{extraction_quality}

**原因**：
- {write_back_reason 或 "tokens 品質不足，無法回寫"}

**建議**：
- 如果 tokens 品質為 "medium" 或 "low"，建議手動檢查並調整
- 或重新在 Stitch 中設計，確保導出的 HTML/CSS 包含完整的設計系統 tokens
```

---

## 產出物

完成本階段後，會生成以下產物：

1. **Design Snapshot Artifact**：
   - Artifact ID：`{snapshot_artifact_id}`
   - 儲存在 workspace artifacts 中
   - Metadata 包含完整的 `DesignSnapshotMetadata`

2. **原始檔案**（如果 project_id 存在）：
   ```
   design_snapshots/{version}/
   ├── original.html  # 安全處理後的 HTML
   └── styles.css     # 安全處理後的 CSS
   ```

3. **Baseline 設定**（如果選擇設定）：
   - `web_generation_baselines` 表中的記錄
   - `baseline_events` 表中的事件記錄

4. **Theme Library 更新**（如果自動回寫成功）：
   - 更新的 theme tokens（typography, spacing, radius, shadow 等）
   - 或新增的 theme archetype
   - 立刻可被 Theme Routing 使用

---

## 品質檢查清單

在完成前，檢查：

- [ ] HTML/CSS 已安全處理（無 script、無 inline handlers）
- [ ] `source_hash` 已計算
- [ ] 解析品質已記錄（`extraction_quality` + `missing_fields`）
- [ ] Metadata 符合 `DesignSnapshotMetadata` schema
- [ ] 原始檔案已儲存到 sandbox（如果 project_id 存在）
- [ ] Artifact 已正確創建
- [ ] 如果設為 baseline，baseline 設定已記錄

---

## 進入下一階段

完成設計快照匯入後，可以：

1. **在 UI 中查看 Snapshot**：在 Artifacts 面板中查看 Design Snapshot Card
2. **設定 Baseline**：在 UI 中將 snapshot 設為 baseline（如果尚未設定）
3. **檢查 Theme Library 更新**（如果自動回寫成功）：
   - 檢查更新的 theme tokens
   - 確認 tokens 已可被 Theme Routing 使用
4. **繼續 web-generation 流程**：
   - 執行 `style_system_gen` playbook（會自動使用更新的 Theme Library）
   - 執行 `page_outline` playbook（會讀取 Design Snapshot 作為參考）
   - 執行 `site_spec_generation` playbook（會整合設計基準）

---

## 注意事項

1. **安全第一**：HTML/CSS 必須經過安全處理，絕不執行任何 script
2. **版本化**：每次匯入都應創建新版本的 snapshot，保持歷史追溯
3. **品質標記**：誠實記錄解析品質，避免假精準
4. **可選增強**：Baseline 設定是可選的，可以在後續 UI 中設定
5. **向後相容**：如果沒有 Design Snapshot，後續 playbook 仍可按原邏輯運行

---

## 技術參考

- **Schema 定義**：`capabilities/web_generation/schema/design_snapshot_schema.py`
- **Theme Fingerprint Extraction**：`capabilities/web_generation/tools/theme_fingerprint_tools.py`
- **Theme Library**：`capabilities/web_generation/schema/theme_library.py`
- **安全策略**：詳見 `docs/ui-engineering-decisions.md` → 決策點 #3
- **版本治理**：詳見 `docs/ui-engineering-decisions.md` → 決策點 #1, #2, #4
- **完整流程**：`docs/complete-pipeline-workflow.md`
- **Stitch 半自動化流程**：`docs-internal/implementation/2025-12-19/unsplash-visual-lens-e2e-testing/stitch-semi-auto-flow-2025-12-20.md`
