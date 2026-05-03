# Unsplash Fingerprints 自動化安裝說明

## 概述

自動化腳本支持從**任意目錄**運行，無需先切換到項目目錄。腳本會自動解析正確的路徑。

## 使用方式

### 方式 1：從任意目錄運行（推薦）

```bash
# 從任何目錄運行，使用絕對路徑
/path/to/mindscape-ai-local-core/scripts/setup_unsplash_fingerprints.sh

# 例如：
~/Projects/mindscape-ai-local-core/scripts/setup_unsplash_fingerprints.sh
```

### 方式 2：從項目根目錄運行

```bash
cd mindscape-ai-local-core
./scripts/setup_unsplash_fingerprints.sh
```

### 方式 3：通過 Python 腳本（支持環境變量控制）

```bash
# 從任意目錄
cd /any/directory
python /path/to/mindscape-ai-local-core/scripts/init_unsplash_fingerprints.py --auto-download

# 或設置環境變量後運行
export UNSPLASH_FINGERPRINTS_ENABLED=true
export HF_TOKEN="your_token"
python /path/to/mindscape-ai-local-core/scripts/init_unsplash_fingerprints.py --auto-download
```

## 路徑解析機制

所有腳本都使用**絕對路徑解析**，確保從任意目錄運行都能正確工作：

1. **Shell 腳本** (`setup_unsplash_fingerprints.sh`):
   - 使用 `$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)` 獲取腳本絕對路徑
   - 自動計算項目根目錄和數據目錄

2. **Python 腳本** (`init_unsplash_fingerprints.py`):
   - 使用 `Path(__file__).resolve()` 獲取絕對路徑
   - 自動解析相對路徑到項目結構

3. **構建腳本** (`build_unsplash_fingerprints.py`):
   - 使用 `Path(__file__).resolve()` 確保導入路徑正確
   - 支持從任意目錄調用

## 驗證安裝

運行測試腳本驗證路徑解析：

```bash
/path/to/mindscape-ai-local-core/scripts/test_path_resolution.sh
```

## 常見問題

### Q: 從不同目錄運行會出錯嗎？

**A:** 不會。所有腳本都使用絕對路徑解析，從任意目錄運行都能正確工作。

### Q: 如何確認腳本找到了正確的路徑？

**A:** 腳本會在開始時顯示：
```
=== Unsplash Dataset Fingerprints Setup ===
```
如果看到錯誤信息，會明確指出缺少的目錄或文件。

### Q: 可以在 Docker 容器內運行嗎？

**A:** 可以，但需要：
1. 確保數據目錄已掛載到容器
2. 設置正確的環境變量（`POSTGRES_HOST`, `POSTGRES_DB` 等）
3. 確保網絡連接可用（下載 Dataset）

### Q: 安裝時自動觸發需要什麼條件？

**A:** 需要設置環境變量：
```bash
export UNSPLASH_FINGERPRINTS_ENABLED=true
export HF_TOKEN="your_token"  # 可選
```

然後在安裝腳本中調用：
```python
from scripts.init_unsplash_fingerprints import setup_fingerprints_if_enabled
setup_fingerprints_if_enabled(auto_download=True)
```

## 測試場景

已測試以下場景，均能正常工作：

1. ✅ 從項目根目錄運行
2. ✅ 從 `scripts/` 目錄運行
3. ✅ 從 `backend/` 目錄運行
4. ✅ 從完全不同的目錄運行（如 `/tmp`）
5. ✅ 使用絕對路徑調用腳本

## 相關文檔

- [詳細使用說明](../backend/scripts/README-UNSPLASH-FINGERPRINTS.md)
- [測試結果文檔](../docs-internal/implementation/2025-12-19/unsplash-visual-lens-e2e-testing/TEST-RESULT-2025-12-20-SUCCESS.md)

