---
playbook_code: obsidian_book_content_generate
version: 1.0.0
capability_code: obsidian_book
name: 生成 Obsidian 書籍內容
description: 從 Mindscape 對話與筆記中整理內容，按照 Obsidian Book Structure Convention 生成結構化的書籍文件到 Obsidian vault
tags:
  - obsidian
  - book
  - content-generation
  - annual

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

language_strategy: model_native
locale: zh-TW
supported_locales:
  - zh-TW
  - en
default_locale: zh-TW
auto_localize: true

entry_agent_type: planner
icon: 📖
---

# 生成 Obsidian 書籍內容 - SOP

## 目標

從今年你在 Mindscape 留下的對話與筆記，按照 Obsidian Book Structure Convention 整理成結構化的書籍內容，輸出到 Obsidian vault。

## 功能說明

這個 Playbook 會：

1. **收集資料**：從本地 Mindscape 資料庫中抓取今年的所有對話與筆記
2. **分月整理**：將資料按月份分組，為每個月生成一個小章節
3. **年度總結**：將 12 個月的章節整合成一份完整的年度年鑑
4. **結構化輸出**：按照 Obsidian Book Structure Convention 輸出到 Obsidian vault，包含完整的 frontmatter

## 執行步驟

### Phase 0: 檢查 Project Context

#### 步驟 0.1: 檢查是否有活躍的 book project
- 檢查 execution context 中是否有 `project_id`
- 如果有，確認 project type 為 `book` 或 `obsidian_book`
- 如果沒有，提示用戶需要先創建 book project

#### 步驟 0.2: 獲取 Obsidian Vault 路徑
- 從 workspace settings 讀取 Obsidian vault 路徑：
  ```python
  workspace = await store.get_workspace(workspace_id)
  vault_paths = workspace.settings.get("obsidian", {}).get("vault_paths", [])
  ```
- 如果有多個 vault，詢問用戶選擇哪一個
- 如果沒有配置 vault 路徑，提示用戶需要先配置

#### 步驟 0.3: 獲取年份和書籍信息
- 從用戶輸入或 project context 獲取年份
- 如果沒有提供，使用當前年份
- 檢查 `books/{year}/` 目錄是否存在
  - 如果不存在，建議用戶先運行 `obsidian_book_structure_init` playbook

### Phase 1: 收集年度資料

#### 步驟 1.1: 查詢 Mindscape 資料庫
- 查詢指定年份的所有對話記錄
- 查詢指定年份的所有筆記
- 過濾只讀取寫給自己的內容（系統只會讀取你與 Mindscape 的對話）

#### 步驟 1.2: 組織資料
- 按時間順序排序
- 按月份分組
- 識別主題和關鍵內容

### Phase 2: 生成月度章節

#### 步驟 2.1: 為每個月生成章節
- 對每個月份（1-12）：
  - 分析該月的對話和筆記內容
  - 識別主要主題和關鍵事件
  - 生成章節標題和描述
  - 生成章節 slug

#### 步驟 2.2: 創建章節目錄結構
- 在 `books/{year}/chapters/` 下創建章節目錄
- 命名格式：`{month-number:02d}-{chapter-slug}`
- 示例：`01-january-reflection`, `02-february-insights`

#### 步驟 2.3: 生成章節文件
- 為每個章節創建 `00-intro.md`（章節介紹）
- 為每個章節創建內容文件（根據內容拆分為多個小節）

**章節介紹文件 (`chapters/{chapter-slug}/00-intro.md`)**：

**Frontmatter**：
```yaml
---
book: "{year}-{book-slug}"
chapter: {chapter_number}
section: 0
slug: "{chapter-slug}"
title: "{章節標題}"
description: "{章節描述}"
status: "draft"
order: {chapter_number}
tags: ["book", "{book-slug}", "month-{month}"]
created_at: "{當前日期}"
updated_at: "{當前日期}"
---
```

**內容**：
```markdown
# {章節標題}

{章節描述}

## 本月重點

{本月的主要內容和重點}

## 小節

- [1. {小節標題}](01-{section-slug}.md)
- [2. {小節標題}](02-{section-slug}.md)
```

### Phase 3: 生成小節內容

#### 步驟 3.1: 分析內容並拆分小節
- 根據內容的主題和長度，將每個月的內容拆分為多個小節
- 每個小節應該有明確的主題
- 小節數量根據內容量決定（通常 2-5 個小節）

#### 步驟 3.2: 生成小節文件
- 為每個小節創建文件：`{section-number:02d}-{section-slug}.md`

**小節文件 Frontmatter**：
```yaml
---
book: "{year}-{book-slug}"
chapter: {chapter_number}
section: {section_number}
slug: "{section-slug}"
title: "{小節標題}"
description: "{小節描述}"
status: "draft"
order: {section_number}
tags: ["book", "{book-slug}", "{相關標籤}"]
created_at: "{當前日期}"
updated_at: "{當前日期}"
---
```

**內容**：
- 從 Mindscape 對話和筆記中提取的相關內容
- 整理和潤色後的文字
- 保持原始內容的脈絡和思考過程

### Phase 4: 更新書籍介紹

#### 步驟 4.1: 更新 `00-intro.md`
- 讀取現有的 `books/{year}/00-intro.md`
- 更新目錄部分，添加所有章節的連結
- 更新書籍描述（如果需要）

#### 步驟 4.2: 更新 `01-chapter-structure.md`
- 讀取現有的 `books/{year}/01-chapter-structure.md`
- 更新章節列表，包含所有生成的章節
- 添加章節規劃說明

### Phase 5: 保存文件

#### 步驟 5.1: 保存所有章節文件
- 使用 `filesystem_write_file` 工具保存所有章節介紹文件
- 使用 `filesystem_write_file` 工具保存所有小節文件
- 確保 frontmatter 格式正確
- 確保文件路徑符合 Obsidian Book Structure Convention

#### 步驟 5.2: 更新書籍級別文件
- 更新 `00-intro.md`（添加目錄）
- 更新 `01-chapter-structure.md`（添加章節列表）

#### 步驟 5.3: 驗證文件創建
- 確認所有文件都已成功創建
- 驗證 frontmatter 格式
- 驗證文件結構符合規範

### Phase 6: 生成摘要

#### 步驟 6.1: 生成內容摘要
- 列出生成的章節數量
- 列出生成的小節數量
- 提供書籍路徑和結構信息

#### 步驟 6.2: 提供後續步驟建議
- 建議用戶在 Obsidian 中查看和編輯內容
- 建議使用 `obsidian_to_site_spec` playbook 生成網站規格
- 提供相關 playbook 的使用說明

## 輸入參數

- `year`（可選）：年份，默認為當前年份
- `book_slug`（可選）：書籍 slug，默認為 "mindscape"
- `vault_path`（可選）：Obsidian vault 路徑（如果沒有在 settings 中配置）
- `content_filter`（可選）：內容過濾條件（如只包含特定標籤的對話）

## 輸出

- 書籍根目錄：`books/{year}/`
- 章節目錄：`books/{year}/chapters/{chapter-slug}/`
- 章節文件：每個章節的 `00-intro.md` 和小節文件
- 更新的書籍介紹：`00-intro.md` 和 `01-chapter-structure.md`

## 預期結果

- ✅ Obsidian vault 中已生成完整的年度書籍結構
- ✅ 所有文件都帶有符合規範的 frontmatter
- ✅ 內容按照月份和主題組織
- ✅ 用戶可以在 Obsidian 中查看、編輯和進一步完善內容

## 注意事項

- **資料隱私**：所有資料只存在本地，不會上傳到雲端
- **只讀取寫給自己的內容**：系統只會讀取你與 Mindscape 的對話
- **可預覽修改**：生成後可以先在 Obsidian 中預覽、修改，再決定要不要進一步處理
- **不會自動發佈**：不會自動幫你發佈、寄給任何人
- **需要先初始化結構**：建議先運行 `obsidian_book_structure_init` playbook 初始化書籍結構

## 與 yearly_personal_book 的差異

**yearly_personal_book**（Local Core）：
- 輸出到 `artifacts/` 目錄
- 簡單的 Markdown 文件
- 沒有 frontmatter
- 沒有結構化組織

**obsidian_book_content_generate**（Playbook Cloud）：
- 輸出到 Obsidian vault
- 符合 Obsidian Book Structure Convention
- 完整的 frontmatter
- 結構化的章節和小節組織
- 可以後續生成網站規格

## 相關文檔

- **結構規範**：`docs/obsidian-book-structure-convention.md`
- **Frontmatter Schema**：`docs/frontmatter-schema.yaml`
- **初始化 Playbook**：`obsidian_book_structure_init.md`

