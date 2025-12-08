# 容器目录映射到本机持久化配置指南

## 概述

当您在界面中配置本地文件系统目录时，这些目录需要映射到本机才能实现数据持久化。本指南说明如何配置 Docker volume 挂载。

## 配置方法

### 方法 1: 使用环境变量配置（推荐）

1. **创建或编辑 `.env` 文件**（在项目根目录）：

```bash
# 本地文件系统挂载配置
# macOS/Linux 示例：
HOST_DOCUMENTS_PATH=/Users/yourname/Documents
CONTAINER_DOCUMENTS_PATH=/host/documents

# Windows 示例（在 WSL 或 Git Bash 中）：
# HOST_DOCUMENTS_PATH=/mnt/c/Users/yourname/Documents
# CONTAINER_DOCUMENTS_PATH=/host/documents
```

2. **在 `docker-compose.yml` 中已配置的挂载**：

```yaml
volumes:
  - ${HOST_DOCUMENTS_PATH:-./data/user-documents}:/host/documents:rw
```

3. **在界面中配置路径时**：

- 如果使用挂载点，在界面中输入：`/host/documents/mindscape-ai`
- 系统会自动将数据写入容器内的 `/host/documents/mindscape-ai`
- 数据会持久化到本机的 `${HOST_DOCUMENTS_PATH}/mindscape-ai`

### 方法 2: 直接编辑 docker-compose.yml

1. **编辑 `docker-compose.yml`**，在 `backend` 服务的 `volumes` 部分添加：

```yaml
volumes:
  - ./backend:/app/backend:rw
  - ./data:/app/data:rw
  - ./logs:/app/logs:rw
  # 添加您的本机目录挂载
  # macOS/Linux:
  - /Users/yourname/Documents:/host/documents:rw
  # Windows (WSL):
  # - /mnt/c/Users/yourname/Documents:/host/documents:rw
```

2. **重启服务**：

```bash
docker compose down
docker compose up -d
```

## 路径映射说明

### 本机路径 → 容器内路径

| 本机路径 | 容器内路径 | 说明 |
|---------|-----------|------|
| `/Users/yourname/Documents` | `/host/documents` | macOS 用户文档目录 |
| `/home/yourname/Documents` | `/host/documents` | Linux 用户文档目录 |
| `C:\Users\yourname\Documents` | `/host/documents` | Windows（通过 WSL） |

### 在界面中配置

当您在界面中配置本地文件系统时：

1. **使用挂载点路径**（推荐）：
   - 输入：`/host/documents/mindscape-ai`
   - 实际数据位置：`${HOST_DOCUMENTS_PATH}/mindscape-ai`

2. **使用相对路径**（数据在项目目录）：
   - 输入：`./data/documents`
   - 实际数据位置：`./data/documents`（已挂载）

## 常见场景

### 场景 1: 使用用户 Documents 目录

**配置步骤**：

1. 在 `.env` 文件中设置：
```bash
HOST_DOCUMENTS_PATH=/Users/yourname/Documents
```

2. 在界面中配置路径：
```
/host/documents/mindscape-ai
```

3. 数据会保存在：
```
/Users/yourname/Documents/mindscape-ai/
```

### 场景 2: 使用项目 data 目录

**配置步骤**：

1. 无需额外配置（已默认挂载 `./data`）

2. 在界面中配置路径：
```
./data/documents
```

3. 数据会保存在：
```
./data/documents/
```

### 场景 3: 使用自定义目录

**配置步骤**：

1. 在 `.env` 文件中设置：
```bash
HOST_DOCUMENTS_PATH=/path/to/your/custom/directory
```

2. 在界面中配置路径：
```
/host/documents/workspace
```

3. 数据会保存在：
```
/path/to/your/custom/directory/workspace/
```

## 验证挂载

### 检查挂载是否成功

```bash
# 进入容器
docker compose exec backend bash

# 检查挂载点
ls -la /host/documents

# 创建测试文件
echo "test" > /host/documents/test.txt

# 退出容器，检查本机文件
exit
ls -la ${HOST_DOCUMENTS_PATH}/test.txt
```

### 检查权限

确保容器有读写权限：

```bash
# 检查本机目录权限
ls -ld ${HOST_DOCUMENTS_PATH}

# 如果需要，修改权限（谨慎操作）
chmod 755 ${HOST_DOCUMENTS_PATH}
```

## 故障排查

### 问题 1: 目录不存在

**错误**：`Directory does not exist`

**解决**：
- 系统会自动创建目录
- 如果创建失败，检查本机目录权限

### 问题 2: 权限不足

**错误**：`Permission denied`

**解决**：
```bash
# 检查目录权限
ls -ld ${HOST_DOCUMENTS_PATH}

# 修改权限（谨慎操作）
chmod 755 ${HOST_DOCUMENTS_PATH}
```

### 问题 3: 路径不匹配

**错误**：数据没有出现在预期位置

**解决**：
- 确认 `docker-compose.yml` 中的挂载配置正确
- 确认界面中输入的路径使用挂载点前缀（如 `/host/documents/...`）

## 安全注意事项

1. **不要挂载系统目录**：
   - ❌ `/etc`
   - ❌ `/sys`
   - ❌ `/proc`
   - ✅ `/Users/...` 或 `/home/...`

2. **限制访问范围**：
   - 只挂载必要的目录
   - 使用只读挂载（`:ro`）如果不需要写入

3. **检查路径**：
   - 系统会自动检查路径安全性
   - 不安全的路径会被拒绝

## 相关文档

- [Docker Volume 文档](https://docs.docker.com/storage/volumes/)
- [Docker Compose 文档](https://docs.docker.com/compose/)

