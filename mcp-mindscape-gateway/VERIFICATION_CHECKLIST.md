# Gateway MVP 验证清单

**日期**: 2026-01-05
**版本**: MVP v1.0.0

---

## ✅ 基础功能验证

### 1. 项目启动

```bash
cd mcp-mindscape-gateway
npm install
npm run dev
```

**预期输出**:
```
Mindscape MCP Gateway started (MVP)
  - Workspace: default-workspace
  - Mode: single_workspace
  - Base URL: http://localhost:8000
```

- [ ] Gateway 可以正常启动
- [ ] 没有编译错误
- [ ] 配置正确加载

---

### 2. tools/list 验证

**测试命令**（使用 MCP Inspector 或直接调用）:
```json
{
  "jsonrpc": "2.0",
  "id": 1,
  "method": "tools/list",
  "params": {}
}
```

**验证点**:
- [ ] 返回工具列表（Primitive Tools）
- [ ] 返回 Playbook 列表（Macro Tools）
- [ ] 工具命名格式正确：`mindscape.tool.<pack>.<action>`
- [ ] Playbook 命名格式正确：`mindscape.playbook.<pack>.<code>`
- [ ] 内部工具不对外暴露（system.*, migrate, debug, admin）
- [ ] 高风险工具标记为 `mindscape.run.*`（需要 confirm_token）

**示例输出**:
```json
{
  "jsonrpc": "2.0",
  "id": 1,
  "result": {
    "tools": [
      {
        "name": "mindscape.tool.wordpress.list_posts",
        "description": "[Primitive] List WordPress posts",
        "inputSchema": {
          "type": "object",
          "properties": {
            "workspace_id": { "type": "string" },
            "inputs": { "type": "object" }
          },
          "required": ["workspace_id"]
        }
      },
      {
        "name": "mindscape.playbook.wordpress.divi_content_update",
        "description": "[Macro Tool] Divi Content Update\n\n...",
        "inputSchema": { ... }
      }
    ]
  }
}
```

---

### 3. tools/call 验证 - Primitive Tool

**测试命令**:
```json
{
  "jsonrpc": "2.0",
  "id": 2,
  "method": "tools/call",
  "params": {
    "name": "mindscape.tool.wordpress.list_posts",
    "arguments": {
      "workspace_id": "your-workspace-id",
      "inputs": {
        "site_id": "yogacookie.app",
        "per_page": 10
      }
    }
  }
}
```

**验证点**:
- [ ] 可以成功调用 Primitive 工具
- [ ] 返回格式符合 ToolResult schema
- [ ] 参数正确传递到后端
- [ ] 错误处理正确

---

### 4. tools/call 验证 - Macro Tool (Playbook)

**测试命令**:
```json
{
  "jsonrpc": "2.0",
  "id": 3,
  "method": "tools/call",
  "params": {
    "name": "mindscape.playbook.wordpress.divi_content_update",
    "arguments": {
      "workspace_id": "your-workspace-id",
      "inputs": {
        "site_id": "yogacookie.app",
        "page_id": 234843
      }
    }
  }
}
```

**验证点**:
- [ ] 可以成功调用 Playbook
- [ ] 返回 execution_id
- [ ] 返回格式符合 ToolResult schema
- [ ] 参数正确传递到后端

---

### 5. Access Policy 验证

#### 5.1 读操作 → Primitive

**测试工具**: `mindscape.tool.wordpress.list_posts`

**验证点**:
- [ ] 工具命名：`mindscape.tool.*`
- [ ] 不需要 confirm_token
- [ ] 可以直接执行

#### 5.2 写操作 → Governed

**测试工具**: `mindscape.run.wordpress.update_page_content`（如果存在）

**验证点**:
- [ ] 工具命名：`mindscape.run.*`
- [ ] 需要 confirm_token
- [ ] 没有 confirm_token 时返回 `confirmation_required`

**预期响应**（无 confirm_token）:
```json
{
  "status": "confirmation_required",
  "message": "⚠️ 此操作需要確認。請先調用 mindscape.confirm.request 獲取 confirm_token",
  "action": "mindscape.run.wordpress.update_page_content",
  "next_action": {
    "tool": "mindscape.confirm.request",
    "args": { "action": "mindscape.run.wordpress.update_page_content" }
  }
}
```

#### 5.3 系统工具 → Internal

**验证点**:
- [ ] `mindscape.tool.system.*` 不对外暴露
- [ ] `mindscape.tool.*.migrate*` 不对外暴露
- [ ] `mindscape.tool.*.debug*` 不对外暴露

---

### 6. ToolNameResolver 验证

**测试场景**:
1. 工具名包含 pack：`wordpress.list_posts` → `mindscape.tool.wordpress.list_posts`
2. 工具名不包含 pack：`list_posts` + `pack: wordpress` → `mindscape.tool.wordpress.list_posts`
3. 工具名重复 pack：`wordpress.list_posts` + `pack: wordpress` → 去重

**验证点**:
- [ ] 正确解析 pack
- [ ] 避免 pack 重复
- [ ] 正确生成 MCP 工具名
- [ ] 正确从 MCP 工具名解析回 identity

---

## 🐛 常见问题排查

### 问题 1: Gateway 无法启动

**可能原因**:
- 依赖未安装：运行 `npm install`
- TypeScript 编译错误：检查 `npm run build`
- 端口被占用：检查后端服务是否运行

**解决方案**:
```bash
npm install
npm run build
# 检查 dist/ 目录是否有输出
```

### 问题 2: tools/list 返回空数组

**可能原因**:
- 后端服务未运行
- 后端 API 端点不正确
- 网络连接问题

**排查步骤**:
```bash
# 检查后端服务
curl http://localhost:8000/api/v1/tools

# 检查配置
echo $MINDSCAPE_BASE_URL
echo $MINDSCAPE_WORKSPACE_ID
```

### 问题 3: tools/call 执行失败

**可能原因**:
- 工具名格式不正确
- 参数格式不正确
- 后端工具不存在

**排查步骤**:
- 检查工具名是否符合三层命名规范
- 检查参数是否包含 `workspace_id` 和 `inputs`
- 检查后端日志

---

## 📊 测试结果记录

| 测试项 | 状态 | 备注 |
|--------|------|------|
| 项目启动 | ⬜ | |
| tools/list - Primitive | ⬜ | |
| tools/list - Macro | ⬜ | |
| tools/list - Access Policy | ⬜ | |
| tools/call - Primitive | ⬜ | |
| tools/call - Macro | ⬜ | |
| tools/call - Governed | ⬜ | |
| ToolNameResolver | ⬜ | |
| 错误处理 | ⬜ | |

---

## 🎯 下一步

完成 MVP 验证后，可以继续：
1. 实现 ConfirmGuard（confirm_token 验证）
2. 实现 AuditLogger（调用记录）
3. 实现执行状态查询工具（`mindscape.execution.status`）
4. 后端补强（Presets API, Preview API）





