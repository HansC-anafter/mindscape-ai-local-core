# Gateway MVP 测试指南

**日期**: 2026-01-05
**版本**: MVP v1.0.0

---

## 🚀 快速测试

### 步骤 1: 准备环境

```bash
cd mindscape-ai-local-core/mcp-mindscape-gateway

# 安装依赖
npm install

# 编译 TypeScript
npm run build
```

### 步骤 2: 配置环境变量（可选）

```bash
export MINDSCAPE_BASE_URL="http://localhost:8000"
export MINDSCAPE_WORKSPACE_ID="your-workspace-id"
export MINDSCAPE_PROFILE_ID="default-user"
```

### 步骤 3: 运行基础检查

```bash
./test-mcp.sh
```

---

## 🧪 测试方法

### 方法 1: 使用 Node.js 直接测试（推荐）

创建一个简单的测试脚本：

```bash
# 测试 tools/list
echo '{"jsonrpc":"2.0","id":1,"method":"tools/list","params":{}}' | npm run dev

# 测试 tools/call（需要先知道工具名）
echo '{"jsonrpc":"2.0","id":2,"method":"tools/call","params":{"name":"mindscape.tool.wordpress.list_posts","arguments":{"workspace_id":"default-workspace","inputs":{"site_id":"yogacookie.app"}}}}' | npm run dev
```

### 方法 2: 使用 MCP Inspector

1. 安装 MCP Inspector:
```bash
npm install -g @modelcontextprotocol/inspector
```

2. 启动 Gateway:
```bash
npm run dev
```

3. 在另一个终端运行 Inspector:
```bash
mcp-inspector node dist/index.js
```

### 方法 3: 使用 Cursor/Claude Desktop

#### Cursor 配置

在 Cursor 设置中添加 MCP Server 配置：

```json
{
  "mcpServers": {
    "mindscape": {
      "command": "node",
      "args": ["/absolute/path/to/mcp-mindscape-gateway/dist/index.js"],
      "env": {
        "MINDSCAPE_BASE_URL": "http://localhost:8000",
        "MINDSCAPE_WORKSPACE_ID": "your-workspace-id"
      }
    }
  }
}
```

#### Claude Desktop 配置

在 `~/.config/claude/mcp.json` 中添加：

```json
{
  "mcpServers": {
    "mindscape": {
      "command": "node",
      "args": ["/absolute/path/to/mcp-mindscape-gateway/dist/index.js"],
      "env": {
        "MINDSCAPE_BASE_URL": "http://localhost:8000",
        "MINDSCAPE_WORKSPACE_ID": "your-workspace-id"
      }
    }
  }
}
```

---

## 📋 测试用例

### 测试 1: tools/list

**请求**:
```json
{
  "jsonrpc": "2.0",
  "id": 1,
  "method": "tools/list",
  "params": {}
}
```

**预期结果**:
- 返回工具列表
- 工具命名格式：`mindscape.tool.<pack>.<action>`
- Playbook 命名格式：`mindscape.playbook.<pack>.<code>`
- 系统工具不对外暴露

### 测试 2: tools/call - Primitive Tool

**请求**:
```json
{
  "jsonrpc": "2.0",
  "id": 2,
  "method": "tools/call",
  "params": {
    "name": "mindscape.tool.wordpress.list_posts",
    "arguments": {
      "workspace_id": "default-workspace",
      "inputs": {
        "site_id": "yogacookie.app",
        "per_page": 5
      }
    }
  }
}
```

**预期结果**:
- 成功执行
- 返回格式符合 ToolResult schema
- 包含 `status`, `outputs`, `_metadata`

### 测试 3: tools/call - Macro Tool (Playbook)

**请求**:
```json
{
  "jsonrpc": "2.0",
  "id": 3,
  "method": "tools/call",
  "params": {
    "name": "mindscape.playbook.wordpress.divi_content_update",
    "arguments": {
      "workspace_id": "default-workspace",
      "inputs": {
        "site_id": "yogacookie.app",
        "page_id": 234843
      }
    }
  }
}
```

**预期结果**:
- 成功执行
- 返回 `execution_id`
- 返回格式符合 ToolResult schema

### 测试 4: Access Policy - Governed Tool

**请求**（无 confirm_token）:
```json
{
  "jsonrpc": "2.0",
  "id": 4,
  "method": "tools/call",
  "params": {
    "name": "mindscape.run.wordpress.delete_page",
    "arguments": {
      "workspace_id": "default-workspace",
      "inputs": {
        "site_id": "yogacookie.app",
        "page_id": 123
      }
    }
  }
}
```

**预期结果**:
- 返回 `confirmation_required`
- 提示需要 confirm_token
- 提供 `next_action` 建议

---

## 🐛 故障排查

### 问题 1: 编译错误

```bash
# 检查 TypeScript 配置
npm run type-check

# 清理并重新编译
rm -rf dist node_modules
npm install
npm run build
```

### 问题 2: 运行时错误

**检查后端服务**:
```bash
curl http://localhost:8000/api/v1/tools
```

**检查环境变量**:
```bash
echo $MINDSCAPE_BASE_URL
echo $MINDSCAPE_WORKSPACE_ID
```

### 问题 3: 工具列表为空

**可能原因**:
- 后端服务未运行
- 后端 API 端点不正确
- 网络连接问题

**排查步骤**:
1. 检查后端服务状态
2. 检查 Gateway 日志
3. 检查网络连接

---

## 📊 测试结果记录

| 测试项 | 状态 | 备注 |
|--------|------|------|
| 项目编译 | ⬜ | |
| tools/list | ⬜ | |
| tools/call - Primitive | ⬜ | |
| tools/call - Macro | ⬜ | |
| Access Policy | ⬜ | |
| 错误处理 | ⬜ | |

---

## 🎯 下一步

完成基础测试后：
1. 修复发现的问题
2. 实现 ConfirmGuard
3. 实现 AuditLogger
4. 添加执行状态查询工具





