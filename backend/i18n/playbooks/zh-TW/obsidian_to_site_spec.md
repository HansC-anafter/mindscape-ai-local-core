---
playbook_code: obsidian_to_site_spec
version: 1.0.0
capability_code: obsidian_book
name: Obsidian 書籍轉網站規格
description: |
  從結構化的 Obsidian 內容生成網站規格文檔。這是網站生成流程的第二步：從結構化內容生成網站規格。如果內容結構尚未確定，應先使用 obsidian_vault_organize 分析內容並建立專案結構（第一步）。適用於已有結構化內容或專案目錄的情況。支援專案模式（從 .mindscape/websites/{project_id}/content/ 讀取，推薦）和傳統模式（直接掃描 vault 結構）。
tags:
  - obsidian
  - book
  - website
  - site-spec
  - conversion
  - structured-content

kind: user_workflow
interaction_mode:
  - conversational
  - needs_review
visible_in:
  - workspace_tools_panel
  - workspace_playbook_menu

required_tools:
  - filesystem_read_file
  - filesystem_write_file

language_strategy: model_native
locale: zh-TW
supported_locales:
  - zh-TW
  - en
default_locale: zh-TW
auto_localize: true

entry_agent_type: planner
icon: 🔄
---

# Obsidian 書籍轉網站規格 - SOP

## 目標

從結構化的 Obsidian 內容生成 `site_structure.yaml` 網站規格文檔到 Project Sandbox。

**工作流程說明**：
- 這是網站生成流程的**第二步**：從結構化內容生成網站規格
- 如果內容結構尚未確定，應先使用 `obsidian_vault_organize` 分析內容並建立專案結構（第一步）

**支援兩種模式**：
1. **專案模式**：從 `.mindscape/websites/{project_id}/content/` 讀取結構化內容（推薦，長期維護）
2. **傳統模式**：直接掃描 vault 結構（向後相容，需要已有結構）

## 執行步驟

### Phase 0: 檢查 Project Context

#### 步驟 0.1: 檢查是否有活躍的 book 或 website project
- 檢查 execution context 中是否有 `project_id`
- 如果有，確認 project type 為 `book`、`obsidian_book` 或 `website`
- 如果沒有，提示用戶需要先創建 project

#### 步驟 0.2: 獲取 Project Sandbox 路徑
- 如果有 project context，使用 `project_sandbox_manager.get_sandbox_path()` 獲取 sandbox 路徑
- Sandbox 路徑結構：`sandboxes/{workspace_id}/{project_type}/{project_id}/`
- 確保 `spec/` 目錄存在

#### 步驟 0.3: 獲取 Obsidian Vault 路徑
- 從 workspace settings 讀取 Obsidian vault 路徑
- 如果有多個 vault，詢問用戶選擇哪一個
- 如果沒有配置，提示用戶需要先配置

#### 步驟 0.4: 獲取掃描參數
- 從用戶輸入獲取掃描模式：`scan_mode`（可選，預設 "auto"）
  - `"auto"`: 自動檢測結構類型並選擇最佳掃描方式
  - `"convention"`: 使用 Obsidian Book Structure Convention（需要 year）
  - `"flexible"`: 靈活掃描任意結構
- 從用戶輸入獲取年份（可選，用於 convention 模式）
- 從用戶輸入獲取 `root_path`（可選，用於 flexible 模式）
- 如果沒有提供，嘗試從 Obsidian 結構推導

### Phase 1: 掃描內容結構

#### 步驟 1.1: 確定內容來源
- **專案模式**（如果提供了 `website_project_id`）：
  - 使用 `WebsiteProjectManager` 讀取專案配置
  - 從 `.mindscape/websites/{website_project_id}/content/` 讀取結構化內容
  - 使用 `ObsidianBookReader.scan_flexible(root_path=content_dir)`
  - 跳過步驟 1.2-1.3，直接使用專案內容

- **傳統模式**（如果沒有提供 `website_project_id`）：
  - 繼續執行步驟 1.2-1.3

#### 步驟 1.2: 選擇掃描模式（僅傳統模式）
- 如果 `scan_mode="convention"` 且提供了 `year`：
  - 使用 `scan_book_structure(year)` 掃描 Convention 結構
  - 如果失敗，自動降級到 flexible 模式
- 如果 `scan_mode="flexible"`：
  - 使用 `scan_flexible(root_path=root_path)` 掃描任意結構
- 如果 `scan_mode="auto"`（預設）：
  - 使用 `scan_by_convention()` 自動檢測結構類型
  - 如果檢測到 Convention 結構，使用 Convention 模式
  - 否則使用 flexible 模式

#### 步驟 1.3: 執行掃描（僅傳統模式）
- 根據選擇的模式執行掃描
- 收集所有 Markdown 檔案
- 解析 frontmatter（如果存在）
- 從 frontmatter 或檔案名稱提取標題、slug 等信息

#### 步驟 1.4: 構建頁面樹結構
- 如果使用專案模式：
  - 從專案的 `content/` 目錄構建頁面樹
  - 使用專案配置中的結構定義
- 如果使用 Convention 模式：
  - 根據 frontmatter 中的 `chapter` 和 `section` 字段構建層級結構
  - 按照 `order` 字段排序
- 如果使用 flexible 模式：
  - 優先使用 frontmatter 中的 `chapter`/`section` 構建層級
  - 如果沒有 frontmatter，使用檔案目錄結構
  - 如果都沒有，使用扁平結構
- 過濾 `status` 為 "ready" 的頁面（可選，根據需求）

### Phase 2: 解析 Frontmatter

#### 步驟 2.1: 解析書籍級別 Frontmatter
- 從 `00-intro.md` 讀取 frontmatter
- 提取：`book`, `year`, `title`, `description`, `tags`

#### 步驟 2.2: 解析章節 Frontmatter
- 對每個章節的 `00-intro.md`：
  - 提取：`chapter`, `slug`, `title`, `description`, `status`, `order`

#### 步驟 2.3: 解析小節 Frontmatter
- 對每個小節文件：
  - 提取：`chapter`, `section`, `slug`, `title`, `description`, `status`, `order`

### Phase 3: 生成網站規格

#### 步驟 3.1: 構建網站基本信息
- 網站標題：使用書籍標題
- 網站描述：使用書籍描述
- Base URL：`/books/{year}`

#### 步驟 3.2: 構建頁面列表
- 書籍介紹頁面：
  - route: `/`
  - title: 書籍標題
  - source: `/books/{year}/00-intro.md`
  - type: `intro`
  - status: 從 frontmatter 讀取

- 章節頁面：
  - route: `/chapters/{chapter-slug}`
  - title: 章節標題
  - source: `/books/{year}/chapters/{chapter-slug}/00-intro.md`
  - type: `chapter`
  - sections: 小節列表

- 小節頁面：
  - route: `/chapters/{chapter-slug}/{section-slug}`
  - title: 小節標題
  - source: `/books/{year}/chapters/{chapter-slug}/{section-number}-{section-slug}.md`
  - type: `section`
  - status: 從 frontmatter 讀取

#### 步驟 3.3: 構建導航結構
- Top Navigation：
  - 首頁：`/`
  - 章節列表：`/chapters`

- Sidebar Navigation：
  - 根據章節結構構建樹狀導航
  - 包含章節和小節的層級關係

### Phase 4: 生成 YAML 文件

#### 步驟 4.1: 構建 YAML 結構
- 使用 Python 的 `yaml` 庫構建 YAML 結構
- 確保格式符合規範

#### 步驟 4.2: 生成 site_structure.yaml
- 文件路徑：`{sandbox_path}/spec/site_structure.yaml`
- 使用 `filesystem_write_file` 工具保存

**YAML 格式示例**：
```yaml
site:
  title: "{書籍標題}"
  description: "{書籍描述}"
  base_url: "/books/{year}"

pages:
  - route: "/"
    title: "介紹"
    source: "/books/{year}/00-intro.md"
    type: "intro"
    status: "ready"

  - route: "/chapters/{chapter-slug}"
    title: "{章節標題}"
    source: "/books/{year}/chapters/{chapter-slug}/00-intro.md"
    type: "chapter"
    sections:
      - route: "/chapters/{chapter-slug}/{section-slug}"
        title: "{小節標題}"
        source: "/books/{year}/chapters/{chapter-slug}/{section-number}-{section-slug}.md"
        status: "ready"

navigation:
  top:
    - label: "首頁"
      route: "/"
    - label: "章節"
      route: "/chapters"
  sidebar:
    - label: "{章節標題}"
      route: "/chapters/{chapter-slug}"
      children:
        - label: "{小節標題}"
          route: "/chapters/{chapter-slug}/{section-slug}"
```

### Phase 5: 驗證和摘要

#### 步驟 5.1: 驗證生成的 YAML
- 檢查 YAML 格式是否正確
- 檢查必需字段是否都存在
- 檢查路由是否唯一

#### 步驟 5.2: 生成轉換摘要
- 列出掃描到的書籍信息
- 列出生成的頁面數量
- 列出導航結構
- 提供文件路徑

## 輸入參數

- `vault_path`（可選）：Obsidian vault 路徑（如果沒有在 settings 中配置）
- `scan_mode`（可選）：掃描模式
  - `"auto"`（預設）：自動檢測結構類型並選擇最佳掃描方式
  - `"convention"`：使用 Obsidian Book Structure Convention（需要 year）
  - `"flexible"`：靈活掃描任意結構
- `year`（可選）：年份，用於 convention 模式
- `root_path`（可選）：根路徑，用於 flexible 模式（例如 `"mindscape-book"`）
- `book_slug`（可選）：書籍 slug（如果沒有，從 Obsidian 結構推導）
- `filter_status`（可選）：過濾狀態（如只包含 "ready" 的頁面）

**使用範例**：
- Convention 模式：`scan_mode=convention, year=2025`
- Flexible 模式：`scan_mode=flexible, root_path=mindscape-book`
- Auto 模式（推薦）：`scan_mode=auto` 或省略（預設）

## 輸出

- 網站規格文件：`spec/site_structure.yaml`
- 文件位置：Project Sandbox 的 `spec/` 目錄

## 預期結果

- ✅ 成功掃描 Obsidian vault 中的書籍結構
- ✅ 成功解析所有 frontmatter
- ✅ 成功生成 `site_structure.yaml` 文件
- ✅ 文件格式正確，符合網站生成需求

## 技術要點

### Frontmatter 解析

使用 `python-frontmatter` 庫解析 frontmatter：
```python
import frontmatter

with open(file_path, 'r', encoding='utf-8') as f:
    post = frontmatter.load(f)
    metadata = post.metadata
    content = post.content
```

### 文件掃描

**Convention 模式**（遞歸掃描 `books/{year}/` 目錄）：
```python
from pathlib import Path

book_dir = Path(vault_path) / "books" / str(year)
for md_file in book_dir.rglob("*.md"):
    # 處理文件
```

**Flexible 模式**（掃描任意結構）：
```python
from obsidian_book.tools import ObsidianBookReader

reader = ObsidianBookReader(vault_path="/path/to/vault")
structure = reader.scan_flexible(root_path="mindscape-book")
for page in structure["pages"]:
    # 處理頁面
```

### YAML 生成

使用 `pyyaml` 庫生成 YAML：
```python
import yaml

site_structure = {
    "site": {...},
    "pages": [...],
    "navigation": {...}
}

yaml_content = yaml.dump(site_structure, allow_unicode=True, sort_keys=False)
```

## 注意事項

- 需要確保 Obsidian vault 路徑已正確配置
- **Convention 模式**：需要確保書籍結構符合 Obsidian Book Structure Convention
- **Flexible 模式**：支援任意結構，自動從 frontmatter 或檔案結構推導
- **Auto 模式**：自動檢測結構類型並選擇最佳掃描方式
- Frontmatter 可選（但建議使用以獲得更好的結構推導）
- 路由 slug 必須唯一
- 文件路徑使用正斜杠 `/`，符合 Obsidian 的內部路徑格式

## 相關文檔

- **結構規範**：`docs/obsidian-book-structure-convention.md`
- **Frontmatter Schema**：`docs/frontmatter-schema.yaml`
- **網站生成路徑**：`../web_generation/docs/web-generation-path.md`

