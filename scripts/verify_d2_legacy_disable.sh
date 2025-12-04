#!/bin/bash
# D2 階段驗證腳本：驗證 PLAYBOOK_DISABLE_LEGACY=1 設置

set -e

echo "🔍 D2 階段驗證：檢查 PLAYBOOK_DISABLE_LEGACY 設置"
echo ""

# 檢查 .env 文件
if [ -f .env ]; then
    echo "📄 檢查 .env 文件："
    if grep -q "PLAYBOOK_DISABLE_LEGACY" .env; then
        VALUE=$(grep "PLAYBOOK_DISABLE_LEGACY" .env | cut -d '=' -f2)
        echo "   PLAYBOOK_DISABLE_LEGACY=$VALUE"
        if [ "$VALUE" = "1" ]; then
            echo "   ✅ 設置正確（已禁用 legacy fallback）"
        else
            echo "   ⚠️  設置為 $VALUE（應為 1）"
        fi
    else
        echo "   ⚠️  未找到 PLAYBOOK_DISABLE_LEGACY 設置"
    fi
    echo ""
else
    echo "⚠️  .env 文件不存在"
    echo ""
fi

# 檢查環境變量
echo "🌍 檢查當前環境變量："
if [ -n "$PLAYBOOK_DISABLE_LEGACY" ]; then
    echo "   PLAYBOOK_DISABLE_LEGACY=$PLAYBOOK_DISABLE_LEGACY"
    if [ "$PLAYBOOK_DISABLE_LEGACY" = "1" ]; then
        echo "   ✅ 環境變量設置正確"
    else
        echo "   ⚠️  環境變量設置為 $PLAYBOOK_DISABLE_LEGACY（應為 1）"
    fi
else
    echo "   ⚠️  環境變量未設置（將從 .env 文件讀取）"
fi
echo ""

# 運行測試
echo "🧪 運行 D2 驗證測試："
python -m pytest backend/tests/test_d2_legacy_disable.py -v --tb=short
echo ""

# 運行 Legacy API 檢測測試
echo "🔍 運行 Legacy API 檢測測試："
python -m pytest backend/tests/test_no_legacy_playbook_apis.py -v --tb=short
echo ""

echo "✅ 驗證完成"
echo ""
echo "📝 注意事項："
echo "   - 如果後端服務正在運行，需要重啟服務以應用新的環境變量設置"
echo "   - 設置 PLAYBOOK_DISABLE_LEGACY=1 後，任何 legacy fallback 都會拋出 RuntimeError"
echo "   - 請確保所有功能都通過 PlaybookService 正常工作"

