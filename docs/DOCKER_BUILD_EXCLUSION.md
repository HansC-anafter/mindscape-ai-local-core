# Docker 构建排除 Cloud Playbook Packs

**日期：** 2025-12-30
**目的：** 确保 Docker 构建时不会把 cloud playbook packs 带进 image

---

## 问题

Docker 不看 `.gitignore`，会把工作目录的所有内容送进 build context。如果本地安装了 cloud playbook packs，它们会被包含进 Docker image，违反架构隔离原则。

---

## 解决方案

### 1. ✅ 创建/更新 .dockerignore

已创建 `.dockerignore`，排除以下路径：

```dockerignore
# Cloud Playbook Packs (必须排除)
**/playbook-packs/**
backend/playbooks/packs-cloud/**
backend/packs/cloud/**
backend/app/capabilities/**
web-console/src/app/capabilities/**
```

**位置：** `mindscape-ai-local-core/.dockerignore`

---

### 2. ✅ 使用精确的 COPY

所有 Dockerfile 都使用精确的 COPY，而不是 `COPY . .`：

#### Dockerfile.backend

```dockerfile
# ✅ 精确复制 backend 目录
COPY backend/requirements.txt .
COPY backend/ ./backend/
```

#### Dockerfile.frontend

```dockerfile
# ✅ 精确复制 web-console 目录
COPY web-console/package*.json ./
COPY web-console/ ./
```

---

## 验证

### 检查 .dockerignore

```bash
cd mindscape-ai-local-core
cat .dockerignore | grep -E "capabilities|pack|cloud"
```

应该看到：
- `backend/app/capabilities/**`
- `web-console/src/app/capabilities/**`
- `**/playbook-packs/**`
- `backend/playbooks/packs-cloud/**`
- `backend/packs/cloud/**`

### 检查 Dockerfile

```bash
# 检查是否有 COPY . .
grep -r "COPY \. \." mindscape-ai-local-core/Dockerfile*

# 应该没有输出（所有 Dockerfile 都使用精确 COPY）
```

### 测试 Docker 构建

```bash
cd mindscape-ai-local-core

# 测试构建（不会真正构建，只是检查 context）
docker build --dry-run -f Dockerfile.backend .

# 检查 build context 中是否包含 capabilities
docker build -f Dockerfile.backend . 2>&1 | grep -i "capabilities\|pack"
```

---

## 排除路径说明

### backend/app/capabilities/

**原因：** Cloud capability packs 通过 CapabilityInstaller 安装到这里，不应进入 local-core image。

**验证：** `.gitignore` 已排除 `/backend/app/capabilities/`

### web-console/src/app/capabilities/

**原因：** Cloud capability packs 的前端部分，不应进入 local-core image。

**验证：** `.gitignore` 已排除 `/web-console/src/app/capabilities/`

### backend/packs/cloud/ 和 backend/playbooks/packs-cloud/

**原因：** 如果存在这些目录，它们包含 cloud 相关的 playbook packs，不应进入 local-core image。

**验证：** 这些路径在 `.dockerignore` 中被明确排除。

---

## 架构隔离原则

根据 `.gitignore` 的注释：

```
# ============================================
# HARD BARRIER: 禁止 Cloud 组件进入 Local-Core
# ============================================
# 这些路径应该永远为空，如果出现文件则说明架构违规
# 所有通过 CapabilityInstaller 安装的文件都应该被排除
/web-console/src/app/capabilities/
/backend/app/capabilities/
```

**原则：**
- Local-core 是开源、本地优先的核心
- Cloud 组件通过 CapabilityInstaller 安装，不应进入 local-core
- Docker image 必须保持纯净，不包含 cloud 组件

---

## 总结

### ✅ 已完成

1. ✅ 创建 `.dockerignore`，排除 cloud playbook packs
2. ✅ 所有 Dockerfile 使用精确 COPY（不是 `COPY . .`）
3. ✅ 排除路径与 `.gitignore` 一致

### 📝 维护建议

1. **添加新的 cloud pack 路径时**，同时更新 `.gitignore` 和 `.dockerignore`
2. **定期检查** Docker build context 是否包含不应该的文件
3. **CI/CD 验证**：在 CI 中检查 Docker image 不包含 capabilities 目录

---

**最后更新：** 2025-12-30
**维护者：** 开发团队

