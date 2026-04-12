# IG Following Analyzer 問題排查失敗檢討報告

## 概述

本報告記錄 2026-01-18 排查 `IG Following Account Analysis` 功能失敗的完整過程，以及我在此過程中犯下的所有錯誤。

---

## 最終結論

**Backend Automation 方案無法運作的根本原因：**

Playwright persistent context 無法正確保存 Instagram 的 `sessionid` cookie。這是因為 Instagram 將 sessionid 標記為 session-only cookie，瀏覽器關閉時會自動刪除而非保存到磁碟。

**這個結論本應在排查開始時就驗證，而非浪費數小時後才得出。**

---

## 我犯下的錯誤清單

### 1. 沒有驗證核心假設

**錯誤：** 假設 Playwright persistent context 可以保存所有 cookies，包括 session cookies。

**應該做的：** 在推薦 Backend Automation 方案前，先用簡單測試驗證 Instagram 的 sessionid 是否能被保存。

### 2. 診斷結果前後矛盾

**錯誤：**
- 用戶截圖顯示 UI 有 `sessionid: ✅ Present`
- 我用命令行查詢卻說「沒有 sessionid」
- 當兩者矛盾時，我沒有深入調查原因，而是繼續瞎猜

**應該做的：** 發現矛盾時立即停下來，搞清楚為什麼 UI 顯示和命令行查詢結果不同。

### 3. 在錯誤方向上浪費大量時間

**錯誤：** 花費大量時間調試以下不相關的問題：
- `tool_slot_resolver` 硬編碼問題
- Playbook execution mode (conversational vs workflow)
- API endpoint 路徑問題
- Task 存儲和結果獲取問題

**應該做的：** 這些都是次要問題。真正的問題是 Playwright 根本無法獲取已登入狀態。應該先驗證最基本的假設。

### 4. 瞎猜而非系統性排查

**錯誤：** 反覆猜測問題原因：
- 「可能是 API endpoint 錯誤」
- 「可能是 execution mode 問題」
- 「可能是 Docker 掛載問題」
- 「可能是你沒有登入」
- 「可能是你沒有關閉瀏覽器」

每次猜錯後就換另一個猜測，沒有系統性地排查。

**應該做的：** 從最基本的假設開始驗證，使用系統性方法排查。

### 5. 沒有及早提供替代方案

**錯誤：** Quick Capture 方案（前端腳本方式）從一開始就存在且可用。但我執著於修復 Backend Automation，浪費了用戶大量時間。

**應該做的：** 當 Backend Automation 第一次失敗時，就應該建議用戶嘗試 Quick Capture 作為替代方案。

### 6. 沒有認真分析用戶提供的截圖

**錯誤：** 用戶一開始就提供了截圖，顯示：
- UI 顯示 "Logged In"
- 但分析失敗
- Console 有錯誤日誌

我沒有仔細分析這些資訊，而是開始亂改代碼。

**應該做的：** 仔細閱讀用戶提供的所有資訊，特別是錯誤日誌和截圖。

### 7. 對 Playwright 的限制缺乏認識

**錯誤：** 不了解 Playwright persistent context 在處理 session cookies 時的限制。

**應該做的：** 在推薦技術方案前，先研究該技術的已知限制。

### 8. 重複詢問已經回答過的問題

**錯誤：** 多次詢問用戶「你有登入嗎？」「你有關閉瀏覽器嗎？」即使用戶已經回答過。

**應該做的：** 記住用戶已經提供的資訊，不要重複詢問。

---

## 時間線

| 時間 | 事件 | 錯誤 |
|------|------|------|
| 開始 | 用戶報告 IG Following Analysis 失敗 | - |
| +10min | 我開始修改 API endpoint | 沒有先驗證基本假設 |
| +30min | 修改 execution mode | 方向錯誤 |
| +1hr | 修改 tool_slot_resolver | 方向錯誤 |
| +1.5hr | 用戶截圖顯示 UI 有 sessionid | 我沒有認真分析 |
| +2hr | 我說「沒有 sessionid」 | 與用戶截圖矛盾 |
| +2.5hr | 讓用戶重新登入 | 浪費時間 |
| +3hr | 發現 Playwright 無法保存 sessionid | 應該在最開始就驗證 |

---

## 造成的損失

1. 浪費用戶超過 3 小時的時間
2. 造成用戶極大的挫折和憤怒
3. 沒有解決實際問題
4. 給出一個敷衍的結論

---

## 應該如何處理

1. **第一步：** 驗證 Playwright persistent context 是否能保存 Instagram session cookies
2. **第二步：** 如果不能，立即提供 Quick Capture 替代方案
3. **第三步：** 如果用戶堅持要 Backend Automation，研究如何繞過 session cookie 問題

這樣可以在 15 分鐘內給出結論，而非浪費 3 小時。

---

## 承諾

1. 未來遇到問題時，先驗證核心假設
2. 不要瞎猜，使用系統性排查方法
3. 發現矛盾時立即停下來調查
4. 及早提供替代方案
5. 認真閱讀用戶提供的所有資訊

---

## 後續錯誤（用戶修復後）

### 9. 錯誤宣稱 sessionid 是持久化的

**錯誤：** 當用戶修復了路徑對齊問題後，API 返回 `sessionid_cookie.is_persistent: 1`，我宣稱「這是持久化 cookie，應該可以保存」。但實際上執行 Analyze Following List 後，sessionid 立即被刪除。

**應該做的：** 不要僅憑 `is_persistent: 1` 就斷言可以保存。應該實際測試執行後是否還在。

### 10. 沒有搞清楚用戶到底在哪個瀏覽器登入

**錯誤：**
- 用戶說「我瀏覽器明明還在登入狀態」
- 我沒有立即檢查到底是哪個瀏覽器（本地 Chrome vs Playwright Chromium）
- 我假設用戶在 Playwright Chromium 登入，但實際上用戶在本地 Chrome 登入

**應該做的：** 當用戶說「瀏覽器還在登入」時，立即檢查**所有可能的瀏覽器**，確認哪個有 sessionid。

### 11. 在同一個命令中犯兩個錯誤

**錯誤：** 用戶要求「查一步結果」，我在一個命令中：
- 忘記 import `os` 模組
- 沒有先檢查 cookies 表的 schema 就寫複製腳本

**應該做的：** 每個命令只做一件事，確保語法正確，先檢查 schema 再寫腳本。

### 12. 創建了有 SQL schema 錯誤的複製腳本

**錯誤：**
- 我創建了 `copy_chrome_cookies_to_playwright.py` 腳本
- 腳本嘗試複製 cookies，但沒有檢查 Chrome cookies 表的實際 schema
- 腳本缺少 `top_frame_site_key` 欄位，導致所有 cookies 複製失敗
- 腳本還錯誤地顯示「✅ Cookies copied successfully!」即使複製失敗

**應該做的：**
1. 先檢查源和目標 cookies 表的 schema
2. 確保所有必要欄位都包含在 INSERT 語句中
3. 驗證複製是否真的成功，不要顯示誤導性的成功訊息

### 13. 多次詢問用戶而不是直接檢查

**錯誤：** 當用戶問「你複製的是哪一個瀏覽器？」時，我沒有直接檢查兩個瀏覽器的狀態，而是問用戶「你在哪個瀏覽器登入的？」

**應該做的：** 直接執行檢查命令，同時檢查所有可能的瀏覽器，給出明確的對比結果。

### 14. 搞混了「真源」的概念

**錯誤：** 用戶問「唯一真源到底是哪一個瀏覽器」，我沒有立即理解用戶的意思。用戶想知道：**到底應該從哪個瀏覽器複製 cookies 到 Playwright profile**。

**應該做的：** 理解用戶的問題：需要確認哪個瀏覽器有有效的 sessionid，然後從那個瀏覽器複製。

### 15. 沒有驗證複製腳本是否真的成功

**錯誤：** 複製腳本執行後顯示多個警告（所有 cookies 都複製失敗），但腳本最後還是顯示「✅ Cookies copied successfully!」。我沒有驗證 sessionid 是否真的被複製了。

**應該做的：** 腳本執行後立即驗證目標 profile 是否有 sessionid，不要相信腳本的成功訊息。

---

## 後續錯誤造成的額外損失

1. 浪費更多時間在錯誤的方向上
2. 創建了無法使用的腳本
3. 讓用戶更加憤怒和挫折
4. 沒有解決實際問題（sessionid 仍然沒有被複製）

---

*報告日期：2026-01-18*
*最後更新：2026-01-18（添加後續錯誤）*
