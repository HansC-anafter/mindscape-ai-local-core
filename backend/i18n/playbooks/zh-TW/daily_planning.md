---
playbook_code: daily_planning
version: 1.0.0
locale: zh-TW
name: 每日整理 & 優先級
description: 幫助用戶整理每日/每週任務，排優先順序，給出可執行清單
tags:
  - planning
  - daily
  - priority
  - work

kind: user_workflow
interaction_mode:
  - conversational
  - needs_review
visible_in:
  - workspace_tools_panel
  - workspace_playbook_menu

language_strategy: model_native
locale: zh-TW
supported_locales:
  - zh-TW
  - en
default_locale: zh-TW
auto_localize: true

entry_agent_type: planner
mindscape_requirements:
  required_intent_tags:
    - work
    - planning
  optional_intent_tags:
    - focus
    - overwhelm
icon: 🗓
required_tools:
  - sandbox.write_file
  - sandbox.read_file
  - filesystem_write_file
  - filesystem_read_file
scope:
  visibility: system
  editable: false
owner:
  type: system
---

# 每日整理 & 優先級 - SOP

## 目標
幫助用戶整理每日/每週任務，排優先順序，給出可執行清單。

## 執行步驟

### 階段 1: 收集任務
- 詢問用戶今天/本週有哪些待辦事項
- 了解任務的緊急程度和重要性
- 收集任務的相關背景信息

### 階段 2: 優先級排序
- 使用優先級矩陣（緊急/重要）進行分類
- 考慮用戶的工作節奏和時間安排
- 給出建議的執行順序

### 階段 3: 生成可執行清單
- 將任務分解為具體的行動步驟
- 為每個任務設定時間估算
- 提供執行建議和注意事項

## 個性化調整

根據用戶的 Mindscape Profile：
- **角色**: 如果是「創業者」，強調 ROI 和效率
- **工作風格**: 如果偏好「結構化」，提供更詳細的步驟分解
- **偏好語氣**: 如果偏好「直白」，減少客套話

## 與長期意圖的銜接

如果用戶有相關的 Active Intent（如「完成三集群冷啟動 MVP」），在回應中明確提及：
> "因為你正在推進「完成三集群冷啟動 MVP」，我會建議你..."

### 階段 4: 文件生成與保存

#### 步驟 4.1: 保存每日計劃
**必須**使用 `sandbox.write_file` 工具保存每日計劃（首選）或 `filesystem_write_file`（需要人工確認）：

- 文件路徑: `daily_plan.md`（相對路徑，相對於 sandbox 根目錄）
- 內容: 完整的每日計劃，包含所有任務和優先級
- 格式: Markdown 格式

#### 步驟 4.2: 保存任務列表
**必須**使用 `sandbox.write_file` 工具保存任務列表（首選）或 `filesystem_write_file`（需要人工確認）：

- 文件路徑: `task_list.md`（相對路徑，相對於 sandbox 根目錄）
- 內容: 詳細的任務列表，包含時間估算和執行建議
- 格式: Markdown 格式

## 成功標準
- 用戶理解任務優先級
- 獲得可執行的任務清單
- 明確下一步行動
- 所有計劃文檔已保存到文件供後續參考

