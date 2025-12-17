---
playbook_code: project_breakdown
version: 1.0.0
locale: zh-TW
name: 專案拆解 & 里程碑
description: 幫助用戶將專案拆解成階段和里程碑，標註風險與下一步行動
tags:
  - planning
  - project
  - milestone
  - strategy

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
    - project
    - planning
  optional_intent_tags:
    - milestone
    - risk
icon: 📦
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

# 專案拆解 & 里程碑 - SOP

## 目標
幫助用戶將專案拆解成階段和里程碑，標註風險點，並給出下一步行動建議。

## 執行步驟

### 階段 1: 理解專案全貌
- 詢問專案的核心目標和預期成果
- 了解專案的時程和資源限制
- 識別關鍵利害關係人和依賴關係

### 階段 2: 階段劃分
- 將專案分解為主要階段（Phase）
- 為每個階段定義明確的交付物
- 識別階段之間的依賴關係

### 階段 3: 里程碑設定
- 為每個階段設定關鍵里程碑
- 定義里程碑的驗收標準
- 標註每個里程碑的時間節點

### 階段 4: 風險識別
- 識別每個階段的潛在風險
- 評估風險的影響程度和發生機率
- 提供風險緩解建議

### 階段 5: 下一步行動
- 為當前階段給出具體的行動建議
- 列出需要立即處理的任務
- 提供資源和時間估算

## 個性化調整

根據用戶的 Mindscape Profile：
- **角色**: 如果是「系統架構設計者」，提供更技術性的分解方式
- **專業領域**: 如果涉及「多集群架構」，強調技術風險和依賴關係
- **工作風格**: 如果偏好「實驗性」，允許更靈活的里程碑調整

## 與長期意圖的銜接

如果用戶有相關的 Active Intent，在回應中明確提及：
> "因為你正在推進「完成三集群冷啟動 MVP」，我會建議你將專案分為三個階段..."

### 階段 6: 文件生成與保存

#### 步驟 6.1: 保存專案結構
**必須**使用 `sandbox.write_file` 工具保存專案結構（首選）或 `filesystem_write_file`（需要人工確認）：

- 文件路徑: `project_structure.md`（相對路徑，相對於 sandbox 根目錄）
- 內容: 完整的專案結構，包含所有階段、交付物和依賴關係
- 格式: Markdown 格式

#### 步驟 6.2: 保存任務分解
**必須**使用 `sandbox.write_file` 工具保存任務分解（首選）或 `filesystem_write_file`（需要人工確認）：

- 文件路徑: `task_breakdown.md`（相對路徑，相對於 sandbox 根目錄）
- 內容: 詳細的任務分解，包含每個階段的具體任務和行動項目
- 格式: Markdown 格式

#### 步驟 6.3: 保存時間線
**必須**使用 `sandbox.write_file` 工具保存時間線（首選）或 `filesystem_write_file`（需要人工確認）：

- 文件路徑: `timeline.md`（相對路徑，相對於 sandbox 根目錄）
- 內容: 專案時間線，包含所有里程碑的時間節點和驗收標準
- 格式: Markdown 格式

#### 步驟 6.4: 保存風險分析（如適用）
如果識別了風險，**必須**使用 `sandbox.write_file` 工具保存（首選）或 `filesystem_write_file`（需要人工確認）：

- 文件路徑: `risk_analysis.md`（相對路徑，相對於 sandbox 根目錄）
- 內容: 風險識別和緩解建議
- 格式: Markdown 格式

## 成功標準
- 專案被清晰分解為階段和里程碑
- 風險點被識別並有緩解方案
- 用戶明確知道下一步行動
- 所有專案規劃文檔已保存到文件供後續參考

