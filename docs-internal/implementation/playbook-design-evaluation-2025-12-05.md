# Playbook 設計原則評估報告

**日期**: 2025-12-05  
**評估範圍**: 當前 Playbook 實作是否符合設計原則

---

## 設計原則回顧

### 1. md：給 LLM 的「劇本 & 心法」
- **上半部**：YAML frontmatter（playbook_code、entry_agent_type、runtime_tier…）
- **下半部**：SOP 文字、步驟說明、範例對話
- **目的**：決定 Playbook 想達成什麼結果、建議思路、主角風格

### 2. json：把「這齣戲」編成可執行配置
- **描述結構**：playbook_code / name / tags / sop_content
- **標記需求 & 限制**：required_tools / allowed_tools / runtime_tier / runtime.backend
- **（可選）高階流程 Hint**：step list / phases

### 3. 外部工具 & Runtime：讓事情「真的在世界裡發生」
- 真實 side-effect 100% 靠工具 / backend
- WordPress / WooCommerce / Notion / Google Drive / MCP servers
- LangChain 工具 / CRS-hub / semantic-hub / site-hub

---

## 當前實作評估

### ✅ 符合的部分

#### 1. md 文件結構
**位置**: `backend/playbooks/*.yaml` (如 `pdf_ocr_processing.yaml`)

**實作狀態**: ✅ **完全符合**

- ✅ YAML frontmatter 包含：
  - `playbook_code`
  - `entry_agent_type`
  - `version` / `name` / `description` / `tags`
  - `tool_dependencies`
  - `inputs` / `outputs`
  - `scope` / `owner`

- ✅ SOP 內容（frontmatter 之後）：
  - 目標說明
  - 功能說明
  - 執行流程
  - 使用範例
  - 注意事項

**載入機制**: `PlaybookFileLoader.parse_frontmatter()` 正確解析 YAML frontmatter 和 Markdown body

**範例**:
```yaml
---
playbook_code: pdf_ocr_processing
entry_agent_type: planner
tool_dependencies:
  - type: builtin
    name: core_files.ocr_pdf
---
# PDF OCR 文字提取 Playbook
## 目標
處理 PDF 檔案，執行 OCR...
```

#### 2. json 文件結構
**位置**: `backend/playbooks/specs/*.json` (如 `content_drafting.json`)

**實作狀態**: ✅ **基本符合**

- ✅ 描述結構：
  - `playbook_code` / `name` / `version`
  - `kind` (user_workflow / system_tool)

- ✅ 流程定義：
  - `steps[]` - 步驟列表
  - `inputs` / `outputs` - 輸入輸出定義
  - 每個 step 有 `tool` / `inputs` / `outputs` / `depends_on`

**載入機制**: `PlaybookJsonLoader.load_playbook_json()` 正確載入 JSON 定義

**範例**:
```json
{
  "playbook_code": "content_drafting",
  "steps": [
    {
      "id": "understand_requirements",
      "tool": "core_llm.structured_extract",
      "inputs": {...},
      "outputs": {...}
    }
  ]
}
```

#### 3. md + json 結合
**實作狀態**: ✅ **完全符合**

- ✅ `PlaybookRun` 模型結合兩者：
  ```python
  class PlaybookRun:
      playbook: Playbook  # md 內容
      playbook_json: Optional[PlaybookJson]  # json 定義
  ```

- ✅ `PlaybookService.load_playbook_run()` 正確載入兩者

---

### ⚠️ 部分符合 / 需要改進的部分

#### 1. Runtime 配置不完整

**當前實作**:
```python
# backend/app/models/playbook.py:216
runtime_handler: str = Field(
    default="local_llm",
    description="Runtime handler: local_llm, remote_crs, custom"
)
```

**缺失的欄位**:
- ❌ `runtime_tier`: `local | cloud_recommended | cloud_only`
- ❌ `runtime` 配置塊：
  - `runtime.backend`: `local_agent | remote_crs`
  - `runtime.requires`: `["long_context", "job_queue", "multi_tenant"]`
  - `runtime.supports_schedule`: `bool`
  - `runtime.max_expected_duration`: `"PT30M"` (ISO 8601)
  - `runtime.allowed_tools`: `["wordpress.multi_site_stats", ...]`

**建議改進**:
```python
# 在 PlaybookMetadata 中添加
runtime_tier: Optional[str] = Field(
    None,
    description="Runtime tier: local, cloud_recommended, cloud_only"
)

runtime: Optional[Dict[str, Any]] = Field(
    None,
    description="Runtime configuration for cloud execution"
)
# runtime 結構：
# {
#   "backend": "remote_crs",
#   "requires": ["long_context", "job_queue"],
#   "supports_schedule": true,
#   "max_expected_duration": "PT30M",
#   "allowed_tools": [...]
# }
```

#### 2. YAML Frontmatter 缺少 runtime 欄位

**當前狀態**: YAML frontmatter 沒有 `runtime_tier` 和 `runtime` 配置

**建議**: 在 `PlaybookFileLoader` 中支援解析這些欄位

```yaml
---
playbook_code: multi_site_daily_seo_health
runtime_tier: cloud_only
runtime:
  backend: remote_crs
  requires:
    - long_context
    - job_queue
    - multi_tenant
  supports_schedule: true
  max_expected_duration: PT30M
  allowed_tools:
    - wordpress.multi_site_stats
    - seo.serp_api
---
```

#### 3. JSON 定義缺少 runtime 欄位

**當前狀態**: JSON 定義中沒有 runtime 相關欄位

**建議**: 在 `PlaybookJson` 模型中添加 runtime 配置

---

## 總結

### ✅ 已符合的原則

1. **md 文件結構**: 完全符合，YAML frontmatter + SOP 內容
2. **json 文件結構**: 基本符合，有步驟定義和輸入輸出
3. **md + json 結合**: 完全符合，`PlaybookRun` 正確結合兩者
4. **工具依賴聲明**: 符合，`tool_dependencies` 支援 builtin / langchain / mcp

### ⚠️ 需要改進的部分

1. **Runtime 配置不完整**:
   - 缺少 `runtime_tier` 欄位
   - 缺少完整的 `runtime` 配置塊
   - 需要支援 Cloud 執行相關配置

2. **YAML Frontmatter 擴展**:
   - 需要支援 `runtime_tier` 和 `runtime` 欄位解析

3. **JSON Schema 擴展**:
   - 需要在 `PlaybookJson` 模型中添加 runtime 配置

---

## 建議改進方案

### 方案 1: 擴展 PlaybookMetadata 模型

**檔案**: `backend/app/models/playbook.py`

```python
class PlaybookMetadata(BaseModel):
    # ... 現有欄位 ...

    # Runtime tier (新增)
    runtime_tier: Optional[str] = Field(
        None,
        description="Runtime tier: local, cloud_recommended, cloud_only"
    )

    # Runtime configuration (新增)
    runtime: Optional[Dict[str, Any]] = Field(
        None,
        description="Runtime configuration for cloud execution"
    )
```

### 方案 2: 擴展 PlaybookFileLoader

**檔案**: `backend/app/services/playbook_loaders/file_loader.py`

在 `load_playbook_from_file()` 中解析 `runtime_tier` 和 `runtime` 欄位。

### 方案 3: 擴展 PlaybookJson 模型

**檔案**: `backend/app/models/playbook.py`

在 `PlaybookJson` 中添加 runtime 相關欄位。

---

## 結論

**當前實作符合度**: **80%**

- ✅ 核心設計原則（md + json）已完全實作
- ⚠️ Runtime 配置部分需要擴展以支援 Cloud 執行場景
- ✅ 工具依賴和執行流程定義完整

**建議優先級**:
1. **高**: 添加 `runtime_tier` 欄位（簡單，影響大）
2. **中**: 添加完整的 `runtime` 配置塊（支援 Cloud 進階功能）
3. **低**: 擴展 JSON schema 以包含 runtime 配置（如果需要在 JSON 中定義）

---

**評估完成時間**: 2025-12-05  
**評估者**: AI Assistant  
**下次評估建議**: 實作 runtime 配置後重新評估

