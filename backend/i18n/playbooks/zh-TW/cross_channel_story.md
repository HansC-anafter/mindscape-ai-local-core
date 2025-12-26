---
playbook_code: cross_channel_story
version: 1.0.0
name: 跨平台故事線
description: 基於品牌故事線生成跨平台一致內容（網站、社群、課程、電子書）
tags:
  - brand
  - content
  - multi-platform
  - storyline
  - content-generation

kind: user_workflow
interaction_mode:
  - conversational
  - needs_review
visible_in:
  - workspace_tools_panel
  - workspace_playbook_menu

required_tools:
  - sandbox.write_file
  - sandbox.read_file
  - filesystem_write_file
  - filesystem_read_file
  - core_llm.generate
  - core_llm.structured_extract
  - core_export.markdown
  - artifact.create
  - artifact.list
  - cloud_capability.call

language_strategy: model_native
locale: zh-TW
supported_locales:
  - zh-TW
  - en
default_locale: zh-TW
auto_localize: true

entry_agent_type: content_creator
icon: 📖
---

# 📖 跨平台故事線

> **同一條故事主軸，在不同平台用不同形式呈現，但核心訊息一致。**

## 目標

基於品牌故事線（Storyline），為不同平台生成一致的內容：

- 網站頁面（Landing Page、About、Product）
- 社群媒體貼文（IG、FB、Twitter）
- 課程單元（線上課程、工作坊）
- 電子書章節
- 部落格文章
- 其他內容形式

## 責任分配

| 步驟 | 責任 | AI 角色 | 人類角色 |
|------|------|---------|----------|
| 故事線選擇 | 🟡 AI提案 | 列出可用的故事線 | 品牌方選擇主軸 |
| 平台適配 | 🟢 AI自動 | 為每個平台生成適配版本 | 品牌方審核 |
| 內容生成 | 🟢 AI自動 | 生成各平台內容草稿 | 品牌方編輯 |
| 一致性檢查 | 🟡 AI提案 | 檢查跨平台一致性 | 品牌方確認 |
| 品牌 MI 對齊 | 🟡 AI提案 | 檢查是否符合品牌 MI | 品牌方確認 |

---

## Step 1: 收集品牌基礎資料

在開始之前，我需要了解品牌的基礎設定，確保生成內容符合品牌調性。

### 讀取品牌 MI（Mind Identity）

```tool
list_artifacts
workspace_id: {workspace_id}
kind: brand_mi
limit: 1
```

如果沒有品牌 MI，我會提醒用戶先執行 `cis_mind_identity` playbook。

### 讀取品牌 Persona

```tool
list_artifacts
workspace_id: {workspace_id}
kind: brand_persona
limit: 5
```

---

## Step 2: 選擇故事線

首先，我需要知道你要基於哪條故事線來生成內容。

### 讀取可用的故事線

我會從 workspace 中讀取已有的故事線：

```tool
list_artifacts
workspace_id: {workspace_id}
kind: brand_storyline
```

同時，我也會檢查現有的 Executions，看看有哪些 `storyline_tags` 已經在使用：

```tool
list_executions
workspace_id: {workspace_id}
include_storyline_tags: true
limit: 50
```

### 決策卡：故事線選擇

```decision_card
card_id: dc_storyline
type: selection
title: "選擇故事主軸"
question: "你要為哪條故事線生成跨平台內容？"
description: "可以選擇已有的故事線，或輸入新的故事線名稱"
options: [從 artifacts 和 executions 讀取的故事線列表]
allow_custom: true
```

**請品牌方選擇或輸入故事主軸。**

如果選擇了新的故事線，我會先創建一個 `brand_storyline` artifact：

create_artifact
workspace_id: {workspace_id}
playbook_code: cross_channel_story
artifact_type: markdown
title: "Storyline: {故事線名稱}"
summary: "品牌故事主軸：{故事線描述}"
content:
  theme: "{故事線名稱}"
  description: "{故事線描述}"
  key_messages: []
metadata:
  kind: brand_storyline
primary_action_type: view
```

---

## Step 3: 選擇目標平台

基於選定的故事線，選擇要在哪些平台生成內容。

### 平台選項詳解

```yaml
platform_options:
  - platform: website
    description: "網站頁面（Landing Page、About、Product）"
    format: markdown/html
    typical_length: "500-2000 字"
    key_elements: ["標題", "價值主張", "CTA", "視覺建議"]

  - platform: social_media
    description: "社群媒體（IG、FB、Twitter、LinkedIn）"
    format: 短文案 + 圖片建議
    typical_length: "50-300 字"
    key_elements: ["文案", "hashtags", "圖片描述", "互動建議"]
    sub_platforms:
      - instagram
      - facebook
      - twitter
      - linkedin

  - platform: course
    description: "課程單元（線上課程、工作坊）"
    format: 課程大綱 + 講義
    typical_length: "1000-5000 字"
    key_elements: ["學習目標", "課程大綱", "互動環節", "作業建議"]

  - platform: ebook
    description: "電子書章節"
    format: markdown
    typical_length: "2000-8000 字"
    key_elements: ["章節標題", "內容結構", "案例", "總結"]

  - platform: blog
    description: "部落格文章"
    format: markdown
    typical_length: "1000-3000 字"
    key_elements: ["標題", "引言", "正文", "結論", "CTA"]

  - platform: email
    description: "電子報/行銷郵件"
    format: markdown/html
    typical_length: "200-800 字"
    key_elements: ["主旨", "開場", "內容", "CTA"]

  - platform: podcast
    description: "Podcast 腳本"
    format: markdown
    typical_length: "2000-5000 字（對應 30-60 分鐘）"
    key_elements: ["開場", "主要內容", "互動環節", "結尾"]
```

### 決策卡：平台選擇

```decision_card
card_id: dc_platforms
type: multi_selection
title: "選擇目標平台"
question: "要在哪些平台生成內容？可以多選"
description: "建議至少選擇 2-3 個平台，以最大化故事線的覆蓋"
options: [以上平台選項]
min_selections: 1
max_selections: 7
```

---

## Step 4: 讀取品牌 MI 和 Persona 細節

在生成內容之前，我需要詳細了解品牌的調性設定。

### 讀取品牌 MI 詳細內容

```tool
read_artifact
artifact_id: {brand_mi_artifact_id}
```

從品牌 MI 中提取：

- 品牌世界觀（Worldview）
- 價值主張（Value Proposition）
- 品牌紅線（Redlines）
- 品牌人格（Personality）
- 語氣指南（Tone of Voice）

### 讀取相關 Persona

```tool
read_artifact
artifact_id: {brand_persona_artifact_id}
```

了解目標受眾的特質和需求。

---

## Step 5: 生成跨平台內容 🟢

基於選定的故事線、平台和品牌設定，我會為每個平台生成適配的內容。

### 內容生成策略

對於每個選定的平台，我會：

1. **適配平台特性**：根據平台特點調整內容長度、格式、風格
2. **保持核心訊息一致**：所有平台都傳達相同的故事核心
3. **符合品牌調性**：使用品牌 MI 中的語氣、人格、價值主張
4. **遵守品牌紅線**：確保內容不違反品牌紅線

### AI 產出範例

#### 網站頁面

```yaml
website_content:
  platform: website
  page_type: landing_page  # 或 about, product
  title: "[基於故事線和品牌 MI 生成的標題]"
  hero_section:
    headline: "[主標題]"
    subheadline: "[副標題]"
    cta_primary: "[主要行動呼籲]"
    cta_secondary: "[次要行動呼籲]"
  content_sections:
    - section_title: "[區塊標題]"
      content: "[適配網站的長篇內容，符合品牌語氣]"
      visual_suggestion: "[視覺元素建議]"
  brand_alignment:
    worldview_ref: "[對應的品牌世界觀]"
    value_proposition_ref: "[對應的價值主張]"
    tone_score: 0.85  # 符合品牌語氣的評分
```

#### 社群媒體貼文

```yaml
social_media_content:
  platform: instagram
  posts:
    - post_id: "ig_001"
      caption: "[IG 文案，符合品牌語氣，50-300 字]"
      hashtags:
        - "#品牌相關"
        - "#故事線相關"
        - "#行業相關"
      image_suggestion:
        style: "[視覺風格]"
        elements: ["元素1", "元素2"]
        color_palette: "[色彩建議]"
      engagement_tips:
        - "建議發布時間：週三 14:00"
        - "互動建議：詢問問題"
  brand_alignment:
    personality_traits: ["友善", "專業"]
    tone_score: 0.90
```

#### 課程單元

```yaml
course_content:
  platform: course
  unit_title: "[單元標題]"
  learning_objectives:
    - "[學習目標 1]"
    - "[學習目標 2]"
    - "[學習目標 3]"
  content_outline:
    - section: "開場"
      duration: "5 分鐘"
      content: "[內容]"
    - section: "核心概念"
      duration: "20 分鐘"
      content: "[內容]"
    - section: "實作練習"
      duration: "15 分鐘"
      content: "[內容]"
    - section: "總結"
      duration: "5 分鐘"
      content: "[內容]"
  interactive_elements:
    - type: "討論問題"
      question: "[問題]"
    - type: "實作任務"
      task: "[任務描述]"
```

#### 電子書章節

```yaml
ebook_content:
  platform: ebook
  chapter_number: 1
  chapter_title: "[章節標題]"
  content_structure:
    - section: "引言"
      content: "[內容]"
    - section: "主要論述"
      subsections:
        - "[子章節 1]"
        - "[子章節 2]"
        - "[子章節 3]"
      content: "[詳細內容]"
    - section: "案例"
      case_study: "[案例描述]"
    - section: "總結"
      content: "[總結內容]"
  word_count: 3500
  reading_time: "15 分鐘"
```

### 一致性檢查 🟡

生成所有平台內容後，我會進行一致性檢查：

```yaml
consistency_check:
  core_message_alignment:
    score: 0.95
    status: "excellent"
    details:
      - "所有平台都傳達了相同的核心訊息"
      - "關鍵概念在各平台間保持一致"

  brand_tone_alignment:
    score: 0.88
    status: "good"
    details:
      - "大部分內容符合品牌語氣"
      - "1 處需要調整：IG 貼文語氣略顯正式"

  worldview_alignment:
    score: 0.92
    status: "excellent"
    details:
      - "所有內容都體現了品牌世界觀"

  redline_compliance:
    score: 1.0
    status: "perfect"
    details:
      - "所有內容都遵守品牌紅線"
```

### 決策卡：內容審核

```decision_card
card_id: dc_content_review
type: review
title: "跨平台內容審核"
question: "請審核生成的內容，確認是否符合預期"
items:
  - item: "網站頁面"
    status: "pending_review"
    preview: "[內容預覽]"
  - item: "IG 貼文"
    status: "pending_review"
    preview: "[內容預覽]"
  - item: "課程單元"
    status: "pending_review"
    preview: "[內容預覽]"
actions:
  - approve: "通過，創建 Artifacts"
  - revise: "需要修改"
  - regenerate: "重新生成"
```

---

## Step 6: 創建 Artifacts 並標記 Storyline Tags

審核通過後，我會為每個平台創建 Artifact，並標記 `storyline_tags`。

### 創建網站頁面 Artifact

```tool
create_artifact
workspace_id: {workspace_id}
playbook_code: cross_channel_story
artifact_type: markdown
title: "網站頁面 - {頁面類型} - {故事線名稱}"
summary: "{頁面摘要}"
content: {生成的網站內容}
metadata:
  kind: content_draft
  platform: website
  page_type: {landing_page|about|product}
  storyline_tags: ["{選定的故事線}"]
  brand_alignment_score: {一致性評分}
primary_action_type: edit
```

### 創建社群媒體 Artifact

```tool
create_artifact
workspace_id: {workspace_id}
playbook_code: cross_channel_story
artifact_type: markdown
title: "IG 貼文 - {故事線名稱} - {貼文編號}"
summary: "{貼文摘要}"
content: {生成的社群媒體內容}
metadata:
  kind: content_draft
  platform: instagram
  social_platform: instagram
  storyline_tags: ["{選定的故事線}"]
  brand_alignment_score: {一致性評分}
primary_action_type: edit
```

### 創建課程單元 Artifact

```tool
create_artifact
workspace_id: {workspace_id}
playbook_code: cross_channel_story
artifact_type: markdown
title: "課程單元 - {單元標題} - {故事線名稱}"
summary: "{單元摘要}"
content: {生成的課程內容}
metadata:
  kind: content_draft
  platform: course
  storyline_tags: ["{選定的故事線}"]
  brand_alignment_score: {一致性評分}
primary_action_type: edit
```

### 創建電子書章節 Artifact

```tool
create_artifact
workspace_id: {workspace_id}
playbook_code: cross_channel_story
artifact_type: markdown
title: "電子書章節 - {章節標題} - {故事線名稱}"
summary: "{章節摘要}"
content: {生成的電子書內容}
metadata:
  kind: content_draft
  platform: ebook
  chapter_number: {章節編號}
  storyline_tags: ["{選定的故事線}"]
  brand_alignment_score: {一致性評分}
primary_action_type: edit
```

---

## Step 7: 更新 Intent 和 Execution 的 Storyline Tags

為了確保完整的追溯鏈，我會更新相關的 Intent 和 Execution。

### 更新 Intent（如果有的話）

如果這個內容生成是基於某個 Intent，我會更新該 Intent 的 `storyline_tags`：

```tool
update_intent
intent_id: {intent_id}
storyline_tags: ["{選定的故事線}"]
```

### 記錄 Execution

當執行完成時，Execution 會自動記錄 `storyline_tags`，這樣在 Execution Trace 視圖中就能看到完整的追溯鏈。

---

## 產出物

完成本階段後，會生成以下 Artifacts：

```text
artifacts/
├── website_landing_page_{storyline}.md     # 網站頁面
├── instagram_post_{storyline}_001.md        # IG 貼文 #1
├── instagram_post_{storyline}_002.md        # IG 貼文 #2
├── course_unit_{storyline}.md              # 課程單元
├── ebook_chapter_{storyline}.md             # 電子書章節
└── ...
```

所有 Artifacts 都會：

- ✅ 標記相同的 `storyline_tags`
- ✅ 包含品牌對齊評分
- ✅ 記錄平台類型
- ✅ 方便在 Storyline 視覺化視圖中追蹤

---

## 品質檢查清單

在完成前，我會檢查：

- [ ] 所有平台內容的核心訊息一致
- [ ] 內容符合品牌 MI（世界觀、價值主張、人格、語氣）
- [ ] 內容遵守品牌紅線
- [ ] 各平台內容適配平台特性
- [ ] 所有 Artifacts 都正確標記 `storyline_tags`
- [ ] 品牌對齊評分 > 0.8

---

## 進入下一階段

完成跨平台故事線後，可以：

1. **在 Storyline 視覺化視圖中查看**：所有相關內容會自動聚合
2. **繼續為其他故事線生成內容**：重複此流程
3. **進入品牌月度檢視**：使用 `brand_monthly_review` playbook 檢視整體覆蓋率
4. **修正和優化**：根據反饋調整內容

---

## 注意事項

1. **品牌 MI 必須存在**：如果沒有品牌 MI，請先執行 `cis_mind_identity` playbook
2. **故事線可以重複使用**：同一條故事線可以為不同平台多次生成內容
3. **內容可以迭代**：生成的內容是草稿，可以多次編輯和優化
4. **追溯鏈完整**：所有內容都會記錄在 Execution Trace 中，方便追溯決策過程
