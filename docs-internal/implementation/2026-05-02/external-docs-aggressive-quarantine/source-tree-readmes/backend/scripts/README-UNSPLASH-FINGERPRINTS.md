# Unsplash Dataset 指紋庫使用說明

## 概述

此腳本用於從 Unsplash Dataset TSV 文件建立指紋庫，增強 Visual Lens 抽取品質。

**觸發方式**：
- **默認**：手動觸發（需要用戶明確執行）
- **可選自動觸發**：通過環境變量 `UNSPLASH_FINGERPRINTS_ENABLED=true` 在安裝時自動下載和建立

## 前置要求

1. **下載 Dataset**：
   ```bash
   # 從 Hugging Face 下載
   huggingface-cli download image-search-2/unsplash_lite_image_dataset \
     --repo-type dataset \
     --local-dir ./data/unsplash-dataset
   ```

2. **數據庫配置**：
   - 確保 PostgreSQL 數據庫已配置
   - 環境變量 `POSTGRES_HOST`, `POSTGRES_DB`, `POSTGRES_USER`, `POSTGRES_PASSWORD` 已設置
   - 默認連接：`localhost:5432/mindscape_vectors`

## 使用方法

### 方法 1：自動化腳本（推薦）

使用 `setup_unsplash_fingerprints.sh` 自動下載並建立指紋庫：

```bash
cd mindscape-ai-local-core

# 設置 Hugging Face token（可選，如果已登錄可跳過）
export HF_TOKEN="your_huggingface_token"

# 運行自動化腳本
chmod +x scripts/setup_unsplash_fingerprints.sh
./scripts/setup_unsplash_fingerprints.sh
```

**腳本會自動**：
1. 檢查並安裝 `huggingface_hub`（如需要）
2. 下載 Dataset TSV 文件到 `data/unsplash-dataset/`
3. 運行 `build_unsplash_fingerprints.py` 建立指紋庫

### 方法 2：手動下載 + 處理

#### 步驟 1：下載 Dataset

```bash
# 使用 Hugging Face CLI
huggingface-cli download image-search-2/unsplash_lite_image_dataset \
  --repo-type dataset \
  --local-dir ./data/unsplash-dataset
```

#### 步驟 2：建立指紋庫

```bash
cd mindscape-ai-local-core
python backend/scripts/build_unsplash_fingerprints.py \
  --colors data/unsplash-dataset/colors.tsv \
  --keywords data/unsplash-dataset/keywords.tsv \
  --photos data/unsplash-dataset/photos.tsv \
  --collections data/unsplash-dataset/collections.tsv
```

### 參數說明

- `--colors`: colors.tsv 文件路徑（可選，但建議提供）
- `--keywords`: keywords.tsv 文件路徑（可選，但建議提供）
- `--photos`: photos.tsv 文件路徑（可選，但建議提供）
- `--collections`: collections.tsv 文件路徑（可選）
- `--batch-size`: 批量插入大小（默認 1000）

### 最小可行版本（Phase 1）

如果只想處理核心數據（colors + keywords）：

```bash
python backend/scripts/build_unsplash_fingerprints.py \
  --colors data/unsplash-dataset/colors.tsv \
  --keywords data/unsplash-dataset/keywords.tsv \
  --batch-size 2000
```

## 預期輸出

腳本會輸出處理進度：

```
Parsed 1234567 photos with color data from colors.tsv
Parsed 1234567 photos with keyword data from keywords.tsv
Total unique photo IDs: 1234567
Processed 1000/1234567 photos (inserted: 1000, updated: 0)
...
Completed: inserted 1234567, updated 0 fingerprints
```

## 性能指標

- **處理速度**：約 1000-5000 照片/秒（取決於數據庫性能）
- **存儲空間**：約 2-5KB/照片（僅元數據）
- **1M 照片處理時間**：約 10-30 分鐘

## 數據庫表結構

表名：`unsplash_photo_fingerprints`

| 字段 | 類型 | 說明 |
|-----|------|------|
| photo_id | VARCHAR(255) | Primary Key |
| colors | JSONB | 顏色數據（含 coverage, score） |
| keywords | JSONB | 關鍵字數據（含 confidence, source） |
| collections | JSONB | Collection 數據 |
| exif_data | JSONB | EXIF 數據（focal_length, aperture, etc.） |
| ai_description | TEXT | AI 生成的描述 |
| aspect_ratio | FLOAT | 寬高比（如 1.5, 1.777） |

## 故障排查

### 問題：找不到數據庫

**錯誤**：`psycopg2.OperationalError: could not connect to server`

**解決**：
1. 檢查 `POSTGRES_HOST`, `POSTGRES_DB`, `POSTGRES_USER`, `POSTGRES_PASSWORD` 環境變量
2. 確認數據庫服務正在運行
3. 檢查網絡連接

### 問題：TSV 文件格式錯誤

**錯誤**：`KeyError: 'photo_id'`

**解決**：
1. 確認 TSV 文件格式正確（Tab 分隔）
2. 檢查文件頭部是否包含 `photo_id` 列
3. 確認文件編碼為 UTF-8

### 問題：內存不足

**錯誤**：`MemoryError`

**解決**：
1. 減小 `--batch-size`（例如 500）
2. 分批處理文件（只處理部分照片）

## 後續步驟

1. **驗證數據**：
   ```sql
   SELECT COUNT(*) FROM unsplash_photo_fingerprints;
   SELECT photo_id, colors, keywords
   FROM unsplash_photo_fingerprints
   LIMIT 5;
   ```

2. **測試增強效果**：
   - 運行 Visual Lens 抽取 playbook
   - 檢查 `enhance_photos` 步驟是否成功
   - 驗證 Schema 中的增強字段是否填充

3. **性能優化**（可選）：
   - 建立索引：`CREATE INDEX idx_fingerprint_photo_id ON unsplash_photo_fingerprints(photo_id);`
   - 使用 Redis 緩存熱點數據

## 自動觸發（安裝時）

### 通過環境變量啟用

在安裝或初始化時，可以通過環境變量自動觸發：

```bash
# 啟用自動下載和建立指紋庫
export UNSPLASH_FINGERPRINTS_ENABLED=true
export HF_TOKEN="your_huggingface_token"  # 可選，如果已登錄可跳過

# 在安裝腳本中調用
python scripts/init_unsplash_fingerprints.py --auto-download
```

### 整合到安裝流程

如果需要在安裝時自動觸發，可以在安裝腳本中添加：

```python
# 在安裝腳本中（例如 setup.py 或 install.sh）
from scripts.init_unsplash_fingerprints import setup_fingerprints_if_enabled

# 檢查環境變量決定是否自動下載
if os.getenv("UNSPLASH_FINGERPRINTS_ENABLED", "false").lower() == "true":
    setup_fingerprints_if_enabled(
        auto_download=True,
        hf_token=os.getenv("HF_TOKEN")
    )
```

### 為什麼默認不自動觸發？

1. **數據量大**：Dataset 包含 6.5M+ 照片，下載和處理需要時間（10-30 分鐘）
2. **可選功能**：指紋庫增強是可選的，不影響基本功能
3. **需要授權**：需要 Hugging Face token 或 Unsplash 授權
4. **存儲成本**：指紋庫約 2-5GB 存儲空間

**建議**：在生產環境部署時，根據需要手動運行或通過 CI/CD 流程觸發。

## 參考資料

- [Unsplash Dataset on Hugging Face](https://huggingface.co/datasets/image-search-2/unsplash_lite_image_dataset)
- [Phase 1 實現總結](../../docs-internal/implementation/2025-12-19/unsplash-visual-lens-e2e-testing/phase1-implementation-summary-2025-12-20.md)

