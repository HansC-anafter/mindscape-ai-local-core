---
playbook_code: cis_lens_packaging
version: 1.0.0
name: Lens 打包
description: 將完成的 CIS 打包成可複用的 Brand Lens
tags:
  - brand
  - lens
  - packaging
  - cis

kind: user_workflow
interaction_mode:
  - conversational
  - needs_review
visible_in:
  - workspace_tools_panel
  - workspace_playbook_menu

required_tools:
  - core_llm.structured_extract
  - cloud_capability.call
  - filesystem_write_file

language_strategy: model_native
locale: zh-TW
supported_locales:
  - zh-TW
  - en
default_locale: zh-TW
auto_localize: true

entry_agent_type: planner
icon: 📦
capability_code: brand_identity
---

# 📦 Lens 打包

> **將完成的 CIS 打包成可複用的 Brand Lens，讓後續所有產出都經過這顆「品牌腦」。**

## 目標

將完整的 CIS（MI、BI、VI）打包成可複用的 Brand Lens，供後續所有品牌產出使用。

## 責任分配

| 步驟 | 責任 | AI 角色 | 人類角色 |
|------|------|---------|----------|
| 收集 CIS 組件 | 🟢 AI自動 | 收集所有 CIS 資料 | 審核完整性 |
| 打包 Lens | 🟢 AI自動 | 生成 Lens 結構 | 確認最終版本 |

---

## Step 1: 收集 CIS 組件

收集所有已完成的 CIS 組件：
- MI（品牌心智）
- BI（行為場景）
- VI（視覺系統）

```tool
filesystem_read_file
path: spec/mind_identity/
```

```tool
filesystem_read_file
path: spec/behavior_identity/
```

```tool
filesystem_read_file
path: spec/visual_identity/
```

---

## Step 2: 打包 Brand Lens

將所有 CIS 組件打包成 Brand Lens。

```tool
cloud_capability.call
capability: brand_identity
endpoint: cis-mapper/package-lens
params:
  workspace_id: {workspace_id}
  cis_components: {collected_cis_data}
```

---

## Step 3: 驗證 Lens

驗證打包完成的 Brand Lens 是否完整可用。







