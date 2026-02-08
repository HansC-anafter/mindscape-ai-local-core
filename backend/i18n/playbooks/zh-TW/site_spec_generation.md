---
playbook_code: site_spec_generation
version: 1.0.0
capability_code: web_generation
name: 網站規格生成
description: |
  生成完整網站規格文檔（site_spec.yaml）。支援從用戶需求生成，或從現有的 site_structure.yaml 轉換升級。
  這是完整網站生成流程的第一步，定義多頁面結構、導航、主題配置和組件需求。
tags:
  - web
  - planning
  - site-spec
  - multi-page
  - website

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

language_strategy: model_native
locale: zh-TW
supported_locales:
  - zh-TW
  - en
default_locale: zh-TW
auto_localize: true

entry_agent_type: planner
icon: 📐
---

# 網站規格生成 - SOP

## 目標

生成完整網站規格文檔 `spec/site_spec.yaml` 到 Project Sandbox。此規格定義了多頁面結構、導航、主題配置和組件需求，是完整網站生成的基礎。

**工作流程說明**：
- 這是完整網站生成流程的**第一步**：生成網站規格
- 支援兩種模式：
  1. **從需求生成**：從用戶輸入的需求生成完整規格
  2. **從現有規格升級**：從 `site_structure.yaml` 轉換並補充完整規格

## 執行步驟

### Phase 0: 檢查 Project Context

#### 步驟 0.0: 取得 Brand Context

在開始生成網站規格之前，先取得品牌的基礎設定。

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

如果 `has_brand_context = true`，在後續生成步驟中，請參考：

1. **網站主題與調性**：
   - 參考 `brand_mi.vision` 和 `brand_mi.worldview` 來決定網站的核心訊息
   - 參考 `brand_mi.values` 來決定網站要強調的價值
   - 參考 `brand_mi.redlines` 來避免不符合品牌調性的內容

2. **內容結構與功能**：
   - 參考 `brand_personas[].needs` 來設計網站的功能
   - 參考 `brand_personas[].pain_points` 來規劃解決方案

3. **內容主軸**：
   - 參考 `brand_storylines[].theme` 和 `brand_storylines[].key_messages` 來規劃網站的內容結構
   - 可以選擇一個主要的 Storyline 作為網站的核心故事

**Brand Context 來源提示**：

- 如果 `metadata.source = "existing_artifacts"`：使用現有的品牌設定
- 如果 `metadata.source = "auto_generated"`：
  - 這些品牌設定是基於現有數據自動生成的
  - 建議後續執行 `cis_mind_identity` playbook 建立更完整的品牌定義
  - 當前生成的網站規格可以基於這些臨時設定開始，後續可以調整

**如果沒有 Brand Context**：

如果 `has_brand_context = false`：
- 提示用戶：「建議先執行 `cis_mind_identity` playbook 建立品牌設定，這樣生成的網站規格會更符合品牌調性。」
- 可以繼續生成，但提醒「未參考品牌設定，後續可能需要調整」

#### 步驟 0.1: 檢查是否有活躍的 web_page 或 website project
- 檢查 execution context 中是否有 `project_id`
- 如果有，確認 project type 為 `web_page` 或 `website`
- 如果沒有，提示用戶需要先創建 project

#### 步驟 0.2: 獲取 Project Sandbox 路徑
- 使用 `project_sandbox_manager.get_sandbox_path()` 獲取 sandbox 路徑
- Sandbox 路徑結構：`sandboxes/{workspace_id}/{project_type}/{project_id}/`
- 確保 `spec/` 目錄存在

#### 步驟 0.3: 檢查現有規格文件
- 檢查是否存在 `spec/site_structure.yaml`（來自 obsidian_to_site_spec）
- 檢查是否存在 `spec/page.md`（來自 page_outline，單頁規格）
- 根據現有文件決定生成模式

### Phase 1: 確定生成模式

#### 步驟 1.1: 模式選擇
根據現有文件選擇生成模式：

**模式 A: 從 site_structure.yaml 升級**
- 如果存在 `spec/site_structure.yaml`
- 讀取現有結構
- 補充主題配置和組件需求
- 轉換為完整的 `site_spec.yaml`

**模式 B: 從用戶需求生成**
- 如果沒有現有規格文件
- 從用戶輸入收集需求
- 生成完整規格

**模式 C: 從 page.md 擴展**
- 如果存在 `spec/page.md`（單頁規格）
- 詢問用戶是否需要擴展為多頁面網站
- 如果是，收集多頁面需求並生成完整規格

### Phase 2: 需求收集（模式 B 或 C）

#### 步驟 2.1: 網站基礎信息
- **網站標題**：詢問網站標題
- **網站描述**：詢問網站描述和目標
- **Base URL**：確定網站基礎路徑（例如：`/books/2025`）
- **元數據**：收集作者、關鍵字等元數據

#### 步驟 2.2: 頁面規劃
- **頁面數量**：確定需要多少頁面
- **頁面類型**：每頁的類型（intro, chapter, section, landing, custom）
- **頁面結構**：每頁包含的 sections
- **頁面路由**：確定每頁的路由路徑

#### 步驟 2.3: 導航規劃
- **Top Navigation**：頂部導航項目
- **Sidebar Navigation**：側邊欄導航（如果有）
- **Footer Navigation**：頁尾導航（如果有）
- **導航層級**：確定導航的層級結構

#### 步驟 2.4: 主題配置需求
- **色彩偏好**：詢問主色、輔色、強調色偏好
  - 如果有 Brand Context，參考 `brand_mi` 的調性建議色彩方向
  - 如果有 `brand_vi_rules`，優先使用品牌視覺規範中的色彩
- **字體偏好**：詢問標題字體、內文字體偏好
  - 如果有 Brand Context，參考品牌 personality 選擇字體風格
- **風格偏好**：現代、極簡、復古、科技感等
  - 如果有 Brand Context，參考 `brand_mi.worldview` 和 `brand_mi.values` 來決定風格方向
- **響應式需求**：斷點配置需求

#### 步驟 2.5: 組件需求
- **Header**：是否需要頁首，需要哪些功能
- **Footer**：是否需要頁尾，需要哪些內容
- **Section 組件**：需要哪些區塊組件（Features, CTA, About 等）
- **UI 組件**：需要哪些基礎 UI 組件

### Phase 3: 規格生成

#### 步驟 3.1: 構建 SiteInfo
根據收集的信息構建網站基礎信息：
```yaml
site:
  title: "{網站標題}"
  description: "{網站描述}"
  base_url: "{base_url}"
  metadata:
    author: "{作者}"
    keywords: ["{關鍵字1}", "{關鍵字2}"]
```

#### 步驟 3.2: 構建 PageSpec 列表
為每個頁面創建 PageSpec：
```yaml
pages:
  - route: "/"
    title: "首頁"
    type: "intro"
    source: "{來源路徑}"
    sections: ["hero", "about", "features"]
    status: "ready"
    metadata:
      seo_title: "{SEO 標題}"
      seo_description: "{SEO 描述}"
```

#### 步驟 3.3: 構建 NavigationSpec
根據導航規劃構建導航結構：
```yaml
navigation:
  top:
    - label: "首頁"
      route: "/"
    - label: "章節"
      route: "/chapters"
      children:
        - label: "第一章"
          route: "/chapters/chapter-1"
  sidebar:
    - label: "第一章"
      route: "/chapters/chapter-1"
      children:
        - label: "第一節"
          route: "/chapters/chapter-1/section-1"
  footer:
    - label: "關於"
      route: "/about"
```

#### 步驟 3.4: 構建 ThemeConfig
根據主題需求構建主題配置：
```yaml
theme:
  colors:
    primary: "{主色}"
    secondary: "{輔色}"
    accent: "{強調色}"
    neutral: ["{中性色1}", "{中性色2}"]
    semantic:
      success: "#10b981"
      warning: "#f59e0b"
      error: "#ef4444"
      info: "#3b82f6"
  typography:
    heading_font: "{標題字體}"
    body_font: "{內文字體}"
    accent_font: "{強調字體}"
    type_scale:
      h1: "3rem"
      h2: "2rem"
      h3: "1.5rem"
      body: "1rem"
    line_heights:
      h1: 1.2
      h2: 1.3
      body: 1.6
  spacing: [4, 8, 12, 16, 24, 32, 48, 64, 96]
  breakpoints:
    sm: "640px"
    md: "768px"
    lg: "1024px"
    xl: "1280px"
```

#### 步驟 3.5: 構建 ComponentRequirement 列表
根據組件需求構建組件列表：
```yaml
components:
  - component_id: "header"
    component_type: "header"
    required: true
    config:
      show_logo: true
      show_navigation: true
  - component_id: "footer"
    component_type: "footer"
    required: true
    config:
      show_copyright: true
  - component_id: "features_section"
    component_type: "section"
    required: false
    config:
      layout: "grid"
      columns: 3
```

### Phase 4: 從 site_structure.yaml 轉換（模式 A）

#### 步驟 4.1: 讀取現有結構
- 讀取 `spec/site_structure.yaml`
- 解析現有的 site、pages、navigation 結構

#### 步驟 4.2: 轉換 SiteInfo
- 從現有的 `site` 區塊提取基礎信息
- 補充缺失的 metadata

#### 步驟 4.3: 轉換 PageSpec
- 將現有的 `pages` 轉換為 PageSpec 格式
- 確保所有必需字段都有值
- 補充缺失的 sections 和 metadata

#### 步驟 4.4: 轉換 NavigationSpec
- 從現有的 `navigation` 轉換為 NavigationSpec 格式
- 確保導航項目對應到實際頁面

#### 步驟 4.5: 補充主題配置
- 如果現有規格沒有主題配置，詢問用戶或使用預設值
- 生成 ThemeConfig

#### 步驟 4.6: 補充組件需求
- 根據頁面結構推導需要的組件
- 生成 ComponentRequirement 列表

### Phase 5: Schema 驗證

#### 步驟 5.1: 使用 Pydantic Schema 驗證
**必須**使用 `capabilities.web_generation.schema.SiteSpec` 驗證生成的規格：

```python
from capabilities.web_generation.schema import SiteSpec
import yaml

# 讀取生成的 YAML
with open("spec/site_spec.yaml", "r") as f:
    data = yaml.safe_load(f)

# 驗證
try:
    spec = SiteSpec(**data)
    spec.validate_routes()
    print("✅ Schema validation passed")
except Exception as e:
    print(f"❌ Schema validation failed: {e}")
    # 修正錯誤並重新生成
```

#### 步驟 5.2: 驗證路由唯一性
- 確保所有頁面路由唯一
- 確保導航中的路由對應到實際頁面

#### 步驟 5.3: 驗證組件依賴
- 確保標記為 `required: true` 的組件有對應配置
- 檢查組件 ID 的唯一性

### Phase 6: 生成 YAML 文件

#### 步驟 6.1: 生成 site_spec.yaml
**必須**使用 `filesystem_write_file` 工具保存網站規格文檔：

- **文件路徑**：`spec/site_spec.yaml`（在 Project Sandbox 中）
- **完整路徑**：`sandboxes/{workspace_id}/{project_type}/{project_id}/spec/site_spec.yaml`

**YAML 格式**：
```yaml
site:
  title: "{網站標題}"
  description: "{網站描述}"
  base_url: "{base_url}"
  metadata: {}

pages:
  - route: "/"
    title: "首頁"
    type: "intro"
    source: "{來源路徑}"
    sections: []
    status: "ready"
    metadata: {}

navigation:
  top: []
  sidebar: []
  footer: []

theme:
  colors:
    primary: "#0a0a2a"
    secondary: "#ffa0e0"
    accent: "#5C4DFF"
    neutral: []
    semantic: {}
  typography:
    heading_font: "Inter"
    body_font: "Inter"
    accent_font: null
    type_scale: {}
    line_heights: {}
  spacing: [4, 8, 12, 16, 24, 32, 48, 64, 96]
  breakpoints:
    sm: "640px"
    md: "768px"
    lg: "1024px"
    xl: "1280px"

components:
  - component_id: "header"
    component_type: "header"
    required: true
    config: {}
  - component_id: "footer"
    component_type: "footer"
    required: true
    config: {}

version: "1.0.0"
created_at: "{時間戳}"
```

#### 步驟 6.2: 註冊 Artifact
**必須**使用 `artifact_registry.register_artifact` 註冊產出的 artifact：

- **artifact_id**：`site_spec`
- **artifact_type**：`yaml`
- **path**：`spec/site_spec.yaml`
- **metadata**：
  - `site_title`：網站標題
  - `page_count`：頁面數量
  - `created_at`：創建時間

### Phase 7: 執行記錄保存

#### 步驟 7.1: 保存對話歷史
**必須**使用 `filesystem_write_file` 工具保存完整的對話歷史：

- 文件路徑: `artifacts/site_spec_generation/{{execution_id}}/conversation_history.json`
- 內容: 完整的對話歷史（包含所有 user 和 assistant 消息）
- 格式: JSON 格式，包含時間戳和角色信息

#### 步驟 7.2: 保存執行摘要
**必須**使用 `filesystem_write_file` 工具保存執行摘要：

- 文件路徑: `artifacts/site_spec_generation/{{execution_id}}/execution_summary.md`
- 內容:
  - 執行時間
  - 執行 ID
  - Playbook 名稱
  - 生成模式（從需求/從現有規格升級）
  - 主要輸入參數
  - 執行結果摘要
  - 生成的網站規格文檔路徑
  - Schema 驗證結果

## 個人化

基於使用者的 Mindscape 個人檔案：
- **技術等級**：若為「進階」，包含更多技術細節和自訂選項
- **詳細程度**：若偏好「高」，提供更詳細的規劃和建議
- **工作風格**：若偏好「結構化」，提供更清晰的結構和步驟

## 與長期意圖的整合

若使用者有相關的活躍意圖（例如「建立公司網站」），明確引用：
> "由於您正在進行「建立公司網站」，我將專注於創建與您的品牌識別和業務目標一致的網站規格..."

## 成功標準

- 網站規格文檔已生成到 Project Sandbox 的 `spec/site_spec.yaml`
- 文檔符合 `SiteSpec` schema 定義
- Schema 驗證通過（路由唯一性、導航一致性等）
- 所有必需字段都有值
- 主題配置完整
- 組件需求明確
- Artifact 已正確註冊
- 文檔格式清晰，易於後續 playbook 使用

## 注意事項

- **Project Context**：必須在 web_page 或 website project 的 context 中執行
- **Sandbox 路徑**：確保使用 Project Sandbox 路徑，而非 artifacts 路徑
- **Schema 驗證**：必須使用 Pydantic schema 驗證生成的規格
- **向後兼容**：如果沒有 project context，可以降級到 artifacts 路徑（但會提示用戶）
- **格式一致性**：確保生成的 YAML 格式符合 schema 定義

## 相關文檔

- **Schema 定義**：`capabilities/web_generation/schema/site_spec_schema.py`
- **Schema 說明**：`capabilities/web_generation/docs/site_spec_schema.md`
- **完整網站生成流程**：`capabilities/web_generation/docs/complete-pipeline-workflow.md`

