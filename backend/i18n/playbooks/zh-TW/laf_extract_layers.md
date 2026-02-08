## 拆解圖層（MVP）

此 playbook 提供 Layer Asset Forge 的最小可行閉環：

- 輸入一張圖片（建議以 `storage_key` 引用）
- 產出 `composition_manifest.json`（`storage_key` + 可取用 URL）

### 輸入

- `image_ref.storage_key`（建議）
- 或 `image_ref.file_path`（僅限本機測試；跨 pack 不建議）

### MVP 限制

- 目前不做真正的 segmentation / matte refine / inpaint，會把整張圖當作單一 layer 輸出。
- 後續會在同一套 `artifact_ref / storage_key` 協議下逐步替換成真實模型工具。

