# 內部工作文檔

`docs-internal/` 是內部工作文檔入口，不是最終對外文檔區。

## 放置原則

- `docs/`
  - 放穩定、可對外或可長期維護的架構文檔、指南、契約。
- `docs-internal/`
  - 放實作計劃、遷移記錄、驗證結果、排障筆記、內部 runbook。
- repo 根目錄的零散 `*.md`
  - 視為暫存工作稿，不應再繼續堆積。
  - 如果內容仍有價值，應回收進 `docs/` 或 `docs-internal/`。

## 子目錄導覽

- `architecture/`
  - 長期但偏內部的架構討論與 change request。
- `core-architecture/`
  - local-core 核心架構工作文檔與補充說明。
- `implementation/`
  - 依主題或日期歸檔的實作細則、runbook、migration 記錄。
- `debugging/`, `bug-fixes/`, `investigation/`
  - 問題分析、排障、驗證與修復紀錄。
- `design/`, `content/`, `meeting-engine/`, `mind-lens/`
  - 各領域專題的內部草案與設計稿。

## 目前優先入口

- runtime / 本機 preview / GPU executor 相關
  - [`docs-internal/implementation/runtime/`](/Users/shock/Projects_local/workspace/mindscape-ai-local-core/docs-internal/implementation/runtime)
- storage / backup / path convention
  - [`backup-and-doc-organization-convention-2026-03-23.md`](/Users/shock/Projects_local/workspace/mindscape-ai-local-core/docs-internal/implementation/storage/backup-and-doc-organization-convention-2026-03-23.md)

## 新增文檔規則

- 新文檔優先放到既有主題目錄，不要再直接丟 repo 根。
- 如果是「規範 / 慣例 / 入口文檔」，要在本頁補一個 link。
- 如果是一次性 debug note，可放 `debugging/` 或對應 `implementation/<topic>/`。
- 檔名使用 `kebab-case` 或現有日期命名慣例，避免再出現難以搜尋的任意命名。
