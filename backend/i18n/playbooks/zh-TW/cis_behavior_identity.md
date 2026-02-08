---
playbook_code: cis_behavior_identity
version: 1.0.0
name: BI 行為場景
description: 建立品牌行為場景，包括溝通風格、客服腳本、危機處理、衝突立場
tags:
  - brand
  - behavior
  - communication
  - customer-service
  - crisis-management

kind: user_workflow
interaction_mode:
  - conversational
  - needs_review
visible_in:
  - workspace_tools_panel
  - workspace_playbook_menu

required_tools:
  - core_llm.generate
  - core_llm.structured_extract
  - cloud_capability.call

language_strategy: model_native
locale: zh-TW
supported_locales:
  - zh-TW
  - en
default_locale: zh-TW
auto_localize: true

entry_agent_type: consultant
icon: 💬
capability_code: brand_identity
---

# 💬 BI 行為場景

> **品牌不只是視覺，更是每一次互動的語氣和行為。**

## 目標

建立品牌的行為識別系統，包括：
- 溝通風格與語氣
- 客服腳本
- 危機處理策略
- 衝突立場

## 責任分配

| 步驟 | 責任 | AI 角色 | 人類角色 |
|------|------|---------|----------|
| 溝通風格 | 🟡 AI提案 | 生成風格選項 | 品牌方確認 |
| 客服腳本 | 🟡 AI提案 | 生成腳本模板 | 品牌方審核 |
| 危機處理 | 🟡 AI提案 | 生成策略框架 | 品牌方決策 |
| 衝突立場 | 🔴 Only Human | 列出可能衝突 | **品牌方親自決定** |

---

## Step 1: 定義溝通風格

基於 MI 品牌心智，定義品牌的溝通風格。

### 讀取品牌心智

```tool
filesystem_read_file
path: spec/mind_identity/personality.md
```

### AI 產出

基於品牌人格，生成溝通風格選項。

---

## Step 2: 建立客服腳本

基於溝通風格，生成客服腳本模板。

---

## Step 3: 定義危機處理策略

建立品牌危機處理的標準流程。

---

## Step 4: 確認衝突立場

品牌方親自決定在各種衝突情況下的立場。







