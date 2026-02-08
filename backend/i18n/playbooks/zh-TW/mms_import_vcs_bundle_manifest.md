## 匯入 VCS Bundle Manifest

此 playbook 讀取 VCS 的 `manifest.json`，把章節清單匯入 MMS 的 `chapter` 軌道（以 timeline items 表示）。

### 輸入

- `project_id`（MMS 專案）
- `manifest_ref`（VCS manifest 來源：可用 `url` / `file_path` / `manifest` inline）

