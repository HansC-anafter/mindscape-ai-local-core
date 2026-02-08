## 匯入 LAF Composition Manifest

此 playbook 讀取 `layer_asset_forge` 的 `composition_manifest.json`，把 layers 以 timeline items 匯入 MMS 的 `extension` 軌道（MVP：先固定在 0..0）。

### 輸入

- `project_id`（MMS 專案）
- `composition_manifest_ref`（LAF manifest 來源：可用 `url` / `file_path` / inline）

