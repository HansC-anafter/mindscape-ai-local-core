# 發佈專案

為已完成的專案匯出最終資產包和清單檔。

## 目標

為 Video Chapter Studio 專案產生並匯出最終清單檔和資產包，使其可供下游系統使用。

## 輸入需求

- **project_id**：要發佈的專案 ID
- **output_format**（選填）：清單格式（`json` 或 `yaml`，預設：json）
- **include_assets**（選填）：包含資產檔案（預設：true）
- **publish_options**（選填）：發佈設定
  - `storage_target`：目標儲存位置
  - `version_tag`：包的版本標籤
  - `mark_as_final`：標記專案為最終版

## 處理流程

1. **驗證專案**：確認專案已準備好發佈
2. **執行擴展鉤子**：執行領域擴展 `on_publish` 鉤子
3. **產生清單**：建立包含所有章節資料的清單檔
4. **上傳包**：將資產和清單上傳至儲存空間
5. **更新狀態**：將專案標記為已發佈

## 輸出

- **bundle_id**：唯一包識別碼
- **manifest_url**：清單檔 URL
- **asset_urls**：所有包含資產的 URL
- **status**：發佈狀態

## 輸出包結構

```
bundle/
├── manifest.json
├── chapters/
│   ├── chapter_1.json
│   ├── chapter_2.json
│   └── ...
├── thumbnails/
│   ├── chapter_1_start.jpg
│   ├── chapter_1_middle.jpg
│   └── ...
└── metadata/
    ├── quality_report.json
    └── extension_data.json
```

## 注意事項

- 擴展鉤子可將領域特定資料加入清單
- 已發佈的包可被外部系統引用
- 版本標籤支援同一專案的多個版本


