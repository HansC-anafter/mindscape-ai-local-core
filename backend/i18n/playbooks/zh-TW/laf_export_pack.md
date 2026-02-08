# 匯出圖層包

## 目的

匯出圖層和組合描述檔供外部工具使用，如 Multi-Media Studio、video_renderer 或外部編輯軟體。

## 使用時機

- 完成圖層拆解和精修工作流程後
- 準備資產以整合至 Multi-Media Studio 時間線時
- 匯出至外部編輯工具時（Photoshop、After Effects）
- 歸檔完整的圖層組合時

## 輸入

- **job_run_id**（必填）：包含要匯出圖層的工作執行 ID
- **output_format**（選填）：
  - `png_layers`：帶有獨立 alpha 的 PNG 檔案（預設）
  - `psd`：Photoshop 文件（未來）
  - `ae_manifest`：After Effects 相容描述檔（未來）
- **include_metadata**（選填）：在匯出中包含完整元資料（預設：true）

## 流程

1. **載入工作**：取得工作執行和相關圖層資產
2. **打包圖層**：依格式組織圖層檔案
3. **生成描述檔**：建立 composition_manifest.json
4. **上傳**：將匯出包儲存至儲存空間

## 輸出

- **export_pack_ref**：匯出包的引用（artifact_ref 格式）
- **layer_count**：匯出中的圖層數量

## 匯出包結構

```
layer_asset_forge/jobs/{job_id}/exports/
├── layers/
│   ├── layer0.png
│   ├── layer1.png
│   └── ...
├── composition_manifest.json
└── job_run.json（若 include_metadata=true）
```

## 使用範例

```yaml
inputs:
  job_run_id: "job_abc123"
  output_format: "png_layers"
  include_metadata: true
```

## 與 MMS 整合

匯出的 `composition_manifest.json` 可使用 `mms_import_laf_composition_manifest` playbook 直接匯入 Multi-Media Studio。

## 相關 Playbook

- `laf_extract_layers`：初始圖層拆解
- `mms_import_laf_composition_manifest`：匯入至 MMS
- `vr_render_video`：從場景描述檔渲染最終影片
