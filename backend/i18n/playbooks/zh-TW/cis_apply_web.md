---
playbook_code: cis_apply_web
version: 1.0.0
name: 應用：網站生成
description: 基於 CIS Lens 生成網站
tags:
  - brand
  - website
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
  - filesystem_write_file

language_strategy: model_native
locale: zh-TW
supported_locales:
  - zh-TW
  - en
default_locale: zh-TW
auto_localize: true

entry_agent_type: content_creator
icon: 🌐
---

# 🌐 應用：網站生成

> **基於 Brand Lens 生成符合品牌視覺和語氣的網站。**

## 目標

使用已建立的 Brand Lens，生成符合品牌識別的網站規格和內容。

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

### Step 2: 生成網站規格

基於 Brand Lens 和網站需求，生成網站規格。

### Step 3: 生成網站內容

基於 Brand Lens 生成網站內容，確保符合品牌視覺和語氣。

---

## 輸入

- `lens_id`: Brand Lens ID
- `workspace_id`: Workspace ID
- `website_requirements`: 網站需求（可選）

## 輸出

- `website_spec`: 生成的網站規格


