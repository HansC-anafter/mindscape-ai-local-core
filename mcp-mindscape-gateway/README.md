# Mindscape Gateway MCP Server

将 Mindscape Local Core 的 Playbook Packs 能力暴露给外部 MCP Client（Cursor、Claude Desktop 等）。

## 快速开始

### 安装依赖

```bash
npm install
```

### 开发模式

```bash
npm run dev
```

### 构建

```bash
npm run build
npm start
```

## 配置

通过环境变量配置：

```bash
export MINDSCAPE_BASE_URL="http://localhost:8000"
export MINDSCAPE_API_KEY="optional-api-key"
# 以下為可選配置
export MINDSCAPE_WORKSPACE_ID="your-workspace-id"  # 如未設定，將自動創建
export MINDSCAPE_PROFILE_ID="default-user"
```

### Auto-Provision 功能（v1.1）

如果未設定 `MINDSCAPE_WORKSPACE_ID`，Gateway 會自動：
1. 查找名為 "MCP Gateway Workspace" 的現有 workspace
2. 如果找不到，自動創建一個新的 workspace

可透過以下環境變量自訂行為：

```bash
export MINDSCAPE_AUTO_PROVISION="true"              # 啟用自動 provision（預設）
export MINDSCAPE_DEFAULT_WORKSPACE_TITLE="My Workspace"  # 自訂 workspace 名稱
```

### Multi-Workspace Mode（v1.2）

設定 `MINDSCAPE_GATEWAY_MODE=multi_workspace` 可支援多 workspace 模式：

```bash
export MINDSCAPE_GATEWAY_MODE="multi_workspace"
```

在 multi_workspace 模式下，可透過參數指定：
- `workspace_id` — 直接指定 workspace ID
- `surface_user_id` — 外部用戶 ID（如 LINE user ID），會自動查找/創建專屬 workspace
- `surface_type` — 外部 surface 類型（如 "line", "discord"）

## Claude Desktop 配置

在 `~/Library/Application Support/Claude/claude_desktop_config.json` 中添加：

```json
{
  "mcpServers": {
    "mindscape": {
      "command": "/path/to/mcp-mindscape-gateway/run.sh",
      "env": {
        "MINDSCAPE_BASE_URL": "http://localhost:8200",
        "MINDSCAPE_PROFILE_ID": "default-user"
      }
    }
  }
}
```

> **注意**：`run.sh` 會自動找到支援 ES Modules 的 Node.js v18+。

## 文档

- [快速启动指南](../docs-internal/GATEWAY_MVP_QUICK_START_2026-01-05.md)
- [后端缺口分析](../docs-internal/BACKEND_GAP_ANALYSIS_AND_IMPLEMENTATION_PHASES_2026-01-05.md)
- [完整实作方案](../docs-internal/CREATIVE_BRIDGE_AND_MCP_SERVER_IMPLEMENTATION_PLAN_2026-01-05.md)





