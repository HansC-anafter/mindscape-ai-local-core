---
playbook_code: cis_apply_content
version: 1.0.0
name: 應用：內容生成
description: 基於 CIS Lens 生成文案、博客、社群內容
tags:
  - brand
  - content
  - copywriting
  - blog
  - social-media
  - cis-application
  - lens

kind: user_workflow
interaction_mode:
  - conversational
  - needs_review
visible_in:
  - workspace_tools_panel
  - workspace_playbook_menu

required_tools:
  - cloud_capability.call
  - core_llm.generate

language_strategy: model_native
locale: zh-TW
supported_locales:
  - zh-TW
  - en
default_locale: zh-TW
auto_localize: true

entry_agent_type: content_creator
icon: ✍️
capability_code: brand_identity
---

# ✍️ 應用：內容生成

> **基於 Brand Lens 生成符合品牌語氣的文案、博客、社群內容。**

## 目標

使用已建立的 Brand Lens，生成符合品牌識別的各種內容。

## 執行流程

### Step 1: 載入 Brand Lens

```tool
cloud_capability.call
capability: brand_identity
endpoint: cis-mapper/get-lens
params:
  workspace_id: {workspace_id}
  lens_id: {lens_id}
```

### Step 2: 生成內容

基於 Brand Lens 和內容類型，生成符合品牌語氣的內容。

---

## 輸入

- `lens_id`: Brand Lens ID
- `workspace_id`: Workspace ID
- `content_type`: 內容類型（blog, social_media, copywriting, article）
- `content_topic`: 內容主題（可選）

## 輸出

- `generated_content`: 生成的內容







