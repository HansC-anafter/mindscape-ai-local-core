# Backup And Documentation Organization Convention

## 背景

2026-03-23 整理工作樹時，發現 backup 與內部文檔有兩個明確問題：

- backup 路徑不一致
  - 同時出現 `data/backups/`、repo root `backups/`、workspace root `db_backups/`
- 文檔落點不一致
  - `docs/`、`docs-internal/`、repo 根 `*.md` 同時混用

這會造成兩種結果：

- `git status` 持續噪音，容易把 DB dump 或臨時產物誤當成源碼變更
- 重要文檔被大量散落工作稿淹沒，後續直接被略過不看

## 結論

### 1. backup 存放規則

- repo 內暫時性備份：
  - 只允許放在 `<repo>/backups/` 或 `<repo>/.backup/`
  - 必須被 `.gitignore` 忽略
- DB dump / 大型備份：
  - 不放在 repo 受版控路徑內
  - 優先放在 workspace 級集中位置，例如 `/Users/shock/Projects_local/workspace/db_backups/`
  - 或外接碟 / 其他非 repo 路徑
- `*.dump`
  - 一律視為備份產物，不應進 git

### 2. 文檔落點規則

- `docs/`
  - 穩定、對外、長期維護的使用說明與架構文檔
- `docs-internal/`
  - 內部 implementation plan、runbook、migration note、debug note
- repo 根 `*.md`
  - 只容忍短期工作稿
  - 任何仍有價值的內容應在任務收尾前搬入 `docs/` 或 `docs-internal/`

### 3. 命名規則

- 優先使用：
  - `topic-name-YYYY-MM-DD.md`
  - 或沿用既有主題目錄下的穩定命名規則
- 避免：
  - `FINAL_*`, `FIX_*`, `TEMP_*`, `SUMMARY_*` 這類只反映當下情緒、不反映主題的檔名

## 立即執行規則

- local-core `.gitignore` 已補：
  - `backups/`
  - `.backup/`
  - `*.dump`
- 後續新增 backup 時：
  - 先放到 ignore 路徑
  - 不要再把 dump 放進 repo 待提交狀態
- 後續新增內部文檔時：
  - 先找對應主題目錄
  - 如果是規範性文檔，回鏈到 `docs-internal/README.md`

## 建議的後續整理

- 把 repo 根散落的工作稿分三批回收：
  - runtime / execution / architecture
  - capability / pack / migration
  - debug / fix summary / temporary reports
- 對 `docs-internal/` 補主題級索引：
  - `implementation/runtime/README.md`
  - `implementation/storage/README.md`
  - `architecture/README.md`

## 不做的事

- 不把歷史 backup 強行搬動或刪除
- 不把所有舊文檔一次性重命名

這份文檔只先固定「新產物該怎麼放」，避免繼續惡化。
