---
playbook_code: grant_scout
version: 1.0.0
name: 政府補助計畫媒合
description: 自動發現和媒合適合您專案的政府補助計畫
tags:
  - grant
  - funding
  - government
  - application

kind: user_workflow
interaction_mode:
  - conversational
visible_in:
  - workspace_tools_panel
  - workspace_playbook_menu

required_tools:
  - grant_scout.index_grants
  - grant_scout.recall_candidates
  - grant_scout.match_grants
  - grant_scout.generate_draft
  - core_llm.structured_extract

language_strategy: model_native
locale: zh-TW
supported_locales:
  - zh-TW
  - en
default_locale: zh-TW
auto_localize: true

entry_agent_type: researcher
icon: 🔍
capability_code: grant_scout
---

# 政府補助計畫媒合

## 目標

幫助您自動發現和媒合適合專案的政府補助計畫，並生成申請策略。

## 功能說明

這個 Playbook 支援三種操作：

1. **索引補助計畫** (`action: index`)
   - 從政府開放資料平台抓取最新補助計畫清單
   - 結構化資料並存入 Grant Vault
   - 支援多種資料來源（data.gov.tw, IRIX 等）

2. **媒合補助計畫** (`action: match`)
   - 輸入您的專案描述
   - 自動媒合適合的補助計畫
   - 判斷適格性並排序推薦
   - 提供策略提示

3. **生成申請草稿** (`action: draft`)
   - 針對特定補助計畫生成申請策略卡
   - 產出申請大綱與 TODO 清單
   - 映射審查重點到需要的證據

## 使用情境

- **新創公司**: 尋找適合的研發補助
- **中小企業**: 發現數位轉型補助
- **學研機構**: 媒合產學合作計畫

## 輸入

### 共同參數
- `action`: 操作類型 - "index", "match", "draft"（必填）
- `vault_path`: Grant Vault 路徑（預設：vault）

### Index 操作
- `sources`: 資料來源列表（預設：["data.gov.tw"]）

### Match 操作
- `user_input`: 專案描述（必填）

### Draft 操作
- `grant_id`: 補助計畫 ID（必填）

## 輸出

### Index 操作
- `indexed_count`: 索引的計畫數量
- `failed_count`: 失敗數量
- `sources`: 索引的資料來源
- `timestamp`: 索引時間

### Match 操作
- `matched_grants`: 媒合的補助計畫列表（含適配分數）
- `total_candidates`: 候選計畫總數
- `eligible_count`: 適格計畫數量

### Draft 操作
- `strategy_card`: 申請策略卡（關鍵資訊與下一步行動）
- `outline`: 申請書大綱
- `todos`: 待辦事項清單

## 範例使用

### 1. 首次使用：索引補助計畫

```yaml
inputs:
  action: "index"
  sources: ["data.gov.tw"]
```

預期輸出：
- 索引結果（計畫數量、成功/失敗數）
- Grant Vault 中的 YAML 文件

### 2. 媒合補助

```yaml
inputs:
  action: "match"
  user_input: "我們正在開發一個 AI 驅動的語音翻譯產品，目前已完成原型，準備進入市場驗證階段。公司是 2 年前成立的新創，團隊 8 人，實收資本額 500 萬。"
```

預期輸出：
- Top 10 適合的補助計畫
- 每個計畫的適配分數、匹配原因、缺口資訊
- 策略提示

### 3. 生成申請草稿

```yaml
inputs:
  action: "draft"
  grant_id: "moeaic-sbir-2025q1"
```

預期輸出：
- 申請策略卡（為何適合、需要準備什麼）
- 申請書大綱（對應審查重點）
- TODO 清單（文件、證據、聯繫）

## 工作流程

### Index 流程
```
1. 呼叫 grant_scout.index_grants
2. 從 API 抓取資料
3. 映射到 Grant Schema
4. 存入 Grant Vault (YAML)
5. 更新向量索引
```

### Match 流程
```
1. 使用 LLM 結構化專案資訊 (core_llm.structured_extract)
2. 多路召回候選計畫 (grant_scout.recall_candidates)
   - 向量檢索（語義相似度）
   - 關鍵字匹配（精確匹配）
   - 規則匹配（產業/階段）
3. 過濾與排序 (grant_scout.match_grants)
   - 硬約束過濾（期限、地區、資本額）
   - 適格性判斷（LLM）
   - 計算適配分數
4. 返回 Top 10 推薦
```

### Draft 流程
```
1. 載入補助計畫詳情
2. 檢查適格性
3. 生成策略卡（關鍵資訊、下一步行動）
4. 生成申請大綱（對應審查重點）
5. 生成 TODO 清單（文件、證據、聯繫）
```

## 備註

- Grant Vault 預設路徑：`vault/`
- 建議每週執行一次索引以更新資料
- 深度解析需要 LLM API，建議使用高 token 上限的模型
- 資料來源需遵守 robots.txt 與授權條款

## 限制

- 目前僅支援 data.gov.tw 資料源
- 深度解析（PDF 下載）尚未實作
- LLM 適格性判斷為 placeholder，需整合 Local-Core LLM 服務
- 向量檢索整合待完成

## 未來擴展

- 支援更多資料來源（IRIX、部會官網）
- 自動深度解析熱門計畫
- 歷史案例學習
- 申請進度追蹤
- 多人協作編輯

