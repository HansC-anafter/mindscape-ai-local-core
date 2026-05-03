# 快速测试指南

## 🚀 三步测试

### 1. 安装和编译

```bash
cd mcp-mindscape-gateway
npm install
npm run build
```

### 2. 运行基础检查

```bash
npm run test:check
```

这会检查：
- ✅ 依赖是否安装
- ✅ 后端服务是否运行
- ✅ TypeScript 是否编译成功
- ✅ Gateway 是否可以启动

### 3. 运行简单测试

```bash
npm test
```

这会测试 `tools/list` 并显示结果。

---

## 📝 手动测试

### 测试 tools/list

```bash
echo '{"jsonrpc":"2.0","id":1,"method":"tools/list","params":{}}' | npm run dev
```

### 测试 tools/call（需要先知道工具名）

```bash
echo '{"jsonrpc":"2.0","id":2,"method":"tools/call","params":{"name":"mindscape.tool.wordpress.list_posts","arguments":{"workspace_id":"default-workspace","inputs":{"site_id":"yogacookie.app"}}}}' | npm run dev
```

---

## 🔍 查看结果

测试脚本会显示：
- 请求内容
- 响应内容
- 工具数量
- 前 3 个工具名称

---

## ⚠️ 注意事项

1. **确保后端服务运行**: `http://localhost:8000`
2. **检查环境变量**: 如果需要，设置 `MINDSCAPE_WORKSPACE_ID`
3. **查看错误**: 如果有错误，检查 Gateway 的 stderr 输出

---

## 📚 更多信息

- [完整测试指南](./TESTING_GUIDE.md)
- [验证清单](./VERIFICATION_CHECKLIST.md)
- [实施状态](./IMPLEMENTATION_STATUS.md)





