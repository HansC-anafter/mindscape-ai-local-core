---
playbook_code: creator_cold_start
version: 1.0.0
capability_code: walkto_lab
name: 素人創作者冷啟動
description: |
  讓沒有經紀人/編輯能力的素人創作者，在 1 天內完成「Lens → 首週 Feed → 1 場共學 → 回寫 → 可攜帶 Dataset」的完整流程。
  提供低門檻的節奏與治理欄位，讓素人從第 1 天就有可用視角與可交付內容。
tags:
  - walkto
  - creator
  - cold-start
  - onboarding
  - lens
  - feed
  - cohort

kind: user_workflow
interaction_mode:
  - conversational
  - needs_review
visible_in:
  - workspace_tools_panel
  - workspace_playbook_menu

required_tools:
  - walkto_create_lens_card
  - walkto_record_walk_session
  - walkto_writeback_universe
  - walkto_generate_dataset
  - cloud_capability.call

language_strategy: model_native
locale: zh-TW
supported_locales:
  - zh-TW
  - en
default_locale: zh-TW
auto_localize: true

entry_agent_type: coder
icon: 🚀
---

# 素人創作者冷啟動 - SOP

## 目標

讓素人創作者在 **1 天內**完成以下 5 件事，建立可持續的內容交付系統：

1. **Lens 雛型生成**：用 10 個判斷句 + 3 條拒絕規則生成初版 Lens Card
2. **首週 Feed 產出**：生成 3-5 則 $5 Feed 草稿並通過一致性檢查
3. **1 場共學主持**：使用簡版 Walk Script 完成 30 分鐘共學 session
4. **回寫與質檢**：收集用戶偏好並生成回寫卡（含信任證據與規則更新）
5. **可攜帶 Dataset 雛形**：導出首週 Personal Dataset（Markdown/Notion 格式）

**核心價值**：
- 避開「內容要很好」這種空話，直接產出可用視角
- 提供節奏與治理欄位，避免創作者無法帶節奏
- 讓用戶在第一天就帶走可用的資料包

## 執行步驟

### Phase 0: 前置準備

**執行順序**：
1. 步驟 0.0: 收集創作者基本資訊
2. 步驟 0.1: 確認主題與素材盒
3. 步驟 0.2: 設定目標（Lens Feed 或 Annual Track）

#### 步驟 0.0: 收集創作者基本資訊

詢問創作者：
- 你的名字/暱稱
- 你專注的主題領域（例如：咖啡文化、博物館、正念練習）
- 你的目標受眾是誰
- 你希望提供什麼價值

**輸出**：
- `creator_name`: 創作者名稱
- `topic`: 主題領域
- `target_audience`: 目標受眾
- `value_proposition`: 價值主張

#### 步驟 0.1: 確認主題與素材盒

確認創作者是否有：
- 已準備的主題內容
- 可用的素材（照片、筆記、觀察）
- 想要分享的經驗或觀點

如果沒有，引導創作者先準備 3-5 個具體的觀察或故事。

**輸出**：
- `topic_materials`: 主題素材列表
- `available_artifacts`: 可用素材（照片、筆記等）

#### 步驟 0.2: 設定目標

確認創作者想要：
- **選項 A**: 先做 Lens Feed ($5/月) - 每週視角更新
- **選項 B**: 直接做 Annual Track ($29/月) - 完整共學軌道

**輸出**：
- `target_tier`: "lens_feed" 或 "annual_track"

### Phase 1: Lens 雛型生成

**調用子 playbook**: `lens_prototype_generate`

使用 `walkto_create_lens_card` 工具，基於創作者提供的主題與素材，生成：

- **10 個判斷句**：具體、可操作的視角（避開空話）
- **3 條拒絕規則**：明確不推薦/不適合的情況
- **視角模型**：創作者最敏感的是什麼（節奏、氛圍、價格等）

**驗收標準**：
- ✅ 判斷句必須具體（例如：「這家咖啡店適合雨天躲一下，不適合第一次來倫敦的人」）
- ✅ 拒絕規則必須明確（例如：「不推薦給需要安靜工作的人」）
- ✅ 至少產出本週可用的 3 條視角

**輸出**：
- `lens_card`: 生成的 Lens Card
- `lens_id`: Lens 識別碼

### Phase 2: 首週 Feed 產出

**調用子 playbook**: `week1_feed_factory`

基於 Lens Card 與主題素材，生成 3-5 則 Feed 草稿：

1. **生成草稿**：每則包含 1-2 條判斷句 + 簡短觀察
2. **一致性檢查**：確保與 Lens Card 的判斷標準一致
3. **重複度檢查**：避免內容重複
4. **禁語檢查**：避免過度承諾、個資洩露等風險
5. **產出排程稿**：標註發布時間與順序

**驗收標準**：
- ✅ 至少 3 則可用 Feed
- ✅ 通過一致性檢查
- ✅ 通過重複度檢查（重複度 < 20%）
- ✅ 通過禁語檢查（無風險內容）

**輸出**：
- `feed_drafts`: Feed 草稿列表（3-5 則）
- `schedule`: 排程建議

### Phase 3: 1 場共學主持（如選擇 Annual Track）

**僅在 `target_tier == "annual_track"` 時執行**

**調用子 playbook**: `walk_session_host_script`

使用簡版 Walk Script 完成 30 分鐘共學 session：

1. **開場**（5 分鐘）：介紹主題、設定期待、風險提醒
2. **探索**（20 分鐘）：引導參與者觀察、提問、互動
3. **收束**（3 分鐘）：總結本場發現、提出下週任務
4. **回寫引導**（2 分鐘）：引導參與者提供偏好與狀態

**使用工具**: `walkto_record_walk_session`

**驗收標準**：
- ✅ Session 時長 25-35 分鐘
- ✅ 完成開場、探索、收束、回寫引導四段
- ✅ 記錄至少 3 條 lens_notes
- ✅ 收集參與者互動痕跡

**輸出**：
- `walk_session`: 記錄的 Walk Session
- `session_id`: Session 識別碼

### Phase 4: 快速 Audience Intake + 回寫

**併入 `personal_writeback` playbook，但使用簡化流程**

使用 5 個固定問題收集首批用戶狀態與偏好：

1. **狀態問題**：你今天想要什麼樣的體驗？（安靜/社交/探索/放鬆）
2. **偏好問題**：你對價格的敏感度？（低/中/高）
3. **審美問題**：你偏好的氛圍/風格？（用關鍵詞描述）
4. **禁忌問題**：有什麼是你絕對不喜歡的？
5. **信任問題**：這次體驗中，哪個瞬間讓你覺得「被理解」？

**使用工具**: `walkto_writeback_universe`

**驗收標準**：
- ✅ 收集至少 3 個用戶的偏好
- ✅ 每個用戶至少 1 條信任證據
- ✅ 生成至少 1 條個人規則

**輸出**：
- `buyer_universes`: 更新的 Buyer Universe 列表
- `writeback_cards`: 回寫卡列表（含信任證據與規則更新）

### Phase 5: 回寫卡質檢

檢查每個回寫卡是否包含：

- ✅ **至少 1 條信任證據**：用戶在哪個瞬間覺得被理解
- ✅ **至少 1 條規則更新**：從互動中提取的個人選擇規則
- ✅ **狀態映射**：用戶在什麼狀態下偏好什麼

如果不符合，提示創作者補充或重新收集。

**輸出**：
- `quality_report`: 質檢報告
- `validated_writeback_cards`: 通過質檢的回寫卡

### Phase 6: 首批 Dataset 雛形導出

**使用工具**: `walkto_generate_dataset` + export endpoint

把首週回寫與偏好生成一份可下載的 Personal Dataset 雛形：

1. **收集資料**：整合所有用戶的偏好、規則、狀態映射
2. **生成 Dataset**：使用 `format="markdown"` 或 `format="notion"`
3. **驗證完整度**：確保包含 state_map、preferences、rules、next_steps
4. **導出**：產出可下載檔案

**驗收標準**：
- ✅ Dataset 包含至少 3 個用戶的資料
- ✅ 每個用戶至少 3 條規則
- ✅ 每個用戶至少 5 個狀態映射
- ✅ 包含 next_steps（下一步任務）

**輸出**：
- `personal_datasets`: 生成的 Personal Dataset 列表
- `export_files`: 導出檔案（Markdown/Notion 格式）

### Phase 7: 「下一步」提醒腳本生成

生成兩段提醒訊息模板：

1. **24 小時提醒**：
   - 小任務（10-20 分鐘可完成）
   - 回寫入口連結
   - 鼓勵完成回寫

2. **72 小時提醒**：
   - 回顧本週發現
   - 下週預告
   - 持續參與鼓勵

**輸出**：
- `reminder_templates`: 提醒訊息模板
- `next_steps`: 寫入 Dataset 的 next_steps

### Phase 8: 風險/禁區守則（主持安全卡）

生成「主持安全卡」，包含：

1. **過度承諾禁止**：不要承諾「保證有效」「一定適合」
2. **個資保護**：不要詢問或記錄敏感個資
3. **代購責任**：明確代購責任邊界（如適用）
4. **內容邊界**：不要提供醫療、法律等專業建議

**輸出**：
- `safety_card`: 主持安全卡內容
- `rejection_rules_extension`: 延伸的拒絕規則

### Phase 9: 完成檢查與下一步

**完成檢查清單**：

- [ ] Lens Card 已生成並通過驗收
- [ ] 首週 Feed 已產出並通過檢查（3-5 則）
- [ ] 1 場共學已完成（如選擇 Annual Track）
- [ ] 回寫卡已生成並通過質檢
- [ ] Personal Dataset 已導出
- [ ] 提醒腳本已生成
- [ ] 安全卡已提供

**下一步建議**：

1. **第 2 週**：使用 `week1_feed_factory` 繼續產出 Feed
2. **第 2 週**：使用 `walk_session_host_script` 主持第二場共學
3. **持續回寫**：每場後使用 `personal_writeback` 更新個人價值系統
4. **月里程碑**：使用 `personal_dataset_export` 生成完整 Dataset

---

## 工具對應

| 功能 | 工具名稱 | 說明 |
|------|---------|------|
| Lens 創建 | `walkto_create_lens_card` | 創建 Lens Card |
| Session 記錄 | `walkto_record_walk_session` | 記錄 Walk Session |
| Universe 回寫 | `walkto_writeback_universe` | 回寫 Buyer Universe |
| Dataset 生成 | `walkto_generate_dataset` | 生成 Personal Dataset |
| Dataset 導出 | `/dataset/{user_id}/export` | 導出 Dataset |

---

## 驗收標準總結

### 1 天內完成檢查

- ✅ Lens Card 已生成（10 個判斷句 + 3 條拒絕規則）
- ✅ 首週 Feed 已產出（3-5 則，通過檢查）
- ✅ 1 場共學已完成（如選擇 Annual Track）
- ✅ 回寫卡已生成（含信任證據與規則更新）
- ✅ Personal Dataset 已導出（Markdown/Notion 格式）
- ✅ 提醒腳本已生成
- ✅ 安全卡已提供

### 質量門檻

- ✅ 判斷句必須具體（避開空話）
- ✅ Feed 通過一致性/重複度/禁語檢查
- ✅ 回寫卡包含至少 1 條信任證據 + 1 條規則更新
- ✅ Dataset 包含至少 3 條規則 + 5 個狀態映射

---

**最後更新**: 2025-12-21
**維護者**: Mindscape AI Team

