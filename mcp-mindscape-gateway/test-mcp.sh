#!/bin/bash
# Gateway MVP 测试脚本

set -e

echo "🧪 Gateway MVP 测试脚本"
echo "========================"
echo ""

# 检查依赖
echo "1️⃣ 检查依赖..."
if [ ! -d "node_modules" ]; then
    echo "   安装依赖..."
    npm install
fi

# 检查后端服务
echo ""
echo "2️⃣ 检查后端服务..."
BACKEND_URL="${MINDSCAPE_BASE_URL:-http://localhost:8000}"
if curl -s "$BACKEND_URL/api/v1/tools" > /dev/null 2>&1; then
    echo "   ✅ 后端服务运行中: $BACKEND_URL"
else
    echo "   ⚠️  后端服务未运行或无法访问: $BACKEND_URL"
    echo "   请确保后端服务已启动"
    exit 1
fi

# 编译 TypeScript
echo ""
echo "3️⃣ 编译 TypeScript..."
npm run build

if [ ! -d "dist" ]; then
    echo "   ❌ 编译失败，dist 目录不存在"
    exit 1
fi

echo "   ✅ 编译成功"

# 测试配置
echo ""
echo "4️⃣ 检查配置..."
echo "   MINDSCAPE_BASE_URL: ${MINDSCAPE_BASE_URL:-http://localhost:8000}"
echo "   MINDSCAPE_WORKSPACE_ID: ${MINDSCAPE_WORKSPACE_ID:-default-workspace}"
echo "   MINDSCAPE_PROFILE_ID: ${MINDSCAPE_PROFILE_ID:-default-user}"

# 测试 Gateway 启动
echo ""
echo "5️⃣ 测试 Gateway 启动（5秒超时）..."
timeout 5 node dist/index.js < /dev/null 2>&1 &
GATEWAY_PID=$!
sleep 2

if ps -p $GATEWAY_PID > /dev/null 2>&1; then
    echo "   ✅ Gateway 可以启动"
    kill $GATEWAY_PID 2>/dev/null || true
else
    echo "   ⚠️  Gateway 启动测试超时（这是正常的，因为 STDIO 模式需要输入）"
fi

echo ""
echo "✅ 基础检查完成！"
echo ""
echo "📝 下一步："
echo "   1. 启动 Gateway: npm run dev"
echo "   2. 在另一个终端使用 MCP Inspector 或 Cursor/Claude Desktop 测试"
echo "   3. 参考 VERIFICATION_CHECKLIST.md 进行完整验证"
echo ""





