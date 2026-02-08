---
playbook_code: cis_apply_visual
version: 1.0.0
name: 應用：視覺素材
description: 基於 CIS Lens 生成海報、簡報、Banner
tags:
  - brand
  - visual
  - poster
  - presentation
  - banner
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
icon: 🎨
capability_code: brand_identity
---

# 🎨 應用：視覺素材

> **基於 Brand Lens 生成符合品牌視覺識別的海報、簡報、Banner。**

## 目標

使用已建立的 Brand Lens，生成符合品牌視覺識別的各種視覺素材。

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

### Step 2: 生成視覺規格

基於 Brand Lens 和視覺類型，生成符合品牌視覺識別的視覺規格。

---

## 輸入

- `lens_id`: Brand Lens ID
- `workspace_id`: Workspace ID
- `visual_type`: 視覺素材類型（poster, presentation, banner, social_media_image）
- `visual_requirements`: 視覺需求（可選）

## 輸出

- `visual_spec`: 生成的視覺規格







