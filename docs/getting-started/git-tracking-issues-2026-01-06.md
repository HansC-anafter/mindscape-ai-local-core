# Git 跟踪缺失文件问题修复记录

**日期**: 2026-01-06  
**问题**: 从 Git 克隆的新环境在 Docker 构建时出现 `ModuleNotFoundError`  
**原因**: 本地开发使用 volume mount，文件存在但未被 Git 跟踪

---

## 问题背景

### 现象

从 Git 克隆的新环境运行 `docker compose up` 时，backend 服务启动失败，出现多个 `ModuleNotFoundError`：

```
ModuleNotFoundError: No module named 'backend.app.models.runtime_environment'
ModuleNotFoundError: No module named 'backend.app.models.control_knob'
ModuleNotFoundError: No module named 'backend.app.services.stores.control_profile_store'
...
```

### 根本原因

**本地开发环境 vs 新环境差异**：

1. **本地开发环境**：
   - `docker-compose.yml` 使用 volume mount：`./backend:/app/backend:rw`
   - 即使文件未被 Git 跟踪，只要在本地文件系统中存在，容器就能通过 volume mount 访问
   - 因此本地开发不会遇到问题

2. **新环境（从 Git 克隆）**：
   - 文件未被 Git 跟踪，克隆后本地不存在
   - Docker 构建时使用 `COPY backend/ ./backend/`，只复制被 Git 跟踪的文件
   - 容器运行时找不到这些文件，导致 `ModuleNotFoundError`

---

## 发现的问题文件

### 已修复的核心文件（共 16 个）

#### Models (2 个)
1. `backend/app/models/runtime_environment.py` - Runtime 环境模型
2. `backend/app/models/control_knob.py` - 控制旋钮模型

#### Services (6 个)
3. `backend/app/services/stores/control_profile_store.py` - 控制配置存储
4. `backend/app/services/stores/user_playbook_meta_store.py` - 用户 Playbook 元数据存储
5. `backend/app/services/stores/workspace_pinned_playbooks_store.py` - 工作区固定 Playbook 存储
6. `backend/app/services/saved_views_store.py` - 保存视图存储
7. `backend/app/services/runtime_auth_service.py` - Runtime 认证服务
8. `backend/app/services/dashboard_aggregator.py` - Dashboard 聚合器
9. `backend/app/services/dashboard_mappings.py` - Dashboard 映射
10. `backend/app/services/knob_effect_compiler.py` - 控制旋钮效果编译器
11. `backend/app/services/knob_presets.py` - 控制旋钮预设配置

#### Routes (5 个)
12. `backend/app/routes/core/runtime_environments.py` - Runtime 环境管理路由
13. `backend/app/routes/core/runtime_proxy.py` - Runtime 代理路由
14. `backend/app/routes/core/dashboard.py` - Dashboard 路由
15. `backend/app/routes/core/runtime_profile_monitoring.py` - Runtime 配置监控路由
16. `backend/app/routes/core/publish_service.py` - 发布服务路由

### 已删除的 Cloud 特定文件（2 个）

根据架构规范，以下文件不应在 local-core 中，已从 Git 中删除：

1. `backend/app/models/channel_binding.py` - Site-Hub 特定的 channel binding（应在 capability pack 中）
2. `backend/app/models/dashboard.py` - Cloud 特定的 Dashboard 模型（已删除，但 `routes/core/dashboard.py` 保留为 core 功能）

### 其他发现但未添加的文件

以下文件未被代码引用，暂不添加：
- `backend/app/routes/core/egb_routes.py` - 未被引用

---

## 修复过程

### 阶段 1: 问题诊断

1. 用户报告 `ModuleNotFoundError`
2. 发现文件存在于本地但未被 Git 跟踪
3. 理解 volume mount 与 Git 跟踪的差异

### 阶段 2: 文件盘点

1. 使用脚本检查所有未被 Git 跟踪的 Python 文件
2. 检查哪些文件被代码引用
3. 区分 core 功能与 cloud 特定功能

### 阶段 3: 批量修复

1. 添加所有被代码引用的核心文件到 Git
2. 删除 cloud 特定的文件
3. 修复 Pydantic 验证错误

### 阶段 4: 验证

1. 提交所有更改
2. 推送到远程仓库
3. 确保新环境可以正常构建

---

## 相关修复

### Pydantic 验证错误修复

在修复过程中还发现并修复了 `MindscapeProfile` 的 Pydantic 验证问题：

**问题**：
```python
# 错误：直接传入 UserPreferences 实例导致验证失败
preferences=UserPreferences(
    preferred_ui_language='zh-TW',
    preferred_content_language='zh-TW',
    timezone='Asia/Taipei'
)
```

**修复**：
```python
# 正确：传入字典，让 Pydantic 自动验证和转换
preferences={
    'preferred_ui_language': 'zh-TW',
    'preferred_content_language': 'zh-TW',
    'timezone': 'Asia/Taipei'
}
```

**文件**：
- `backend/app/services/mindscape_store.py`
- `backend/app/models/mindscape.py`

---

## 预防措施

### 1. 开发规范

- **新文件必须立即添加到 Git**：创建新文件后立即 `git add`，不要等到提交时
- **定期检查未跟踪文件**：使用 `git status` 检查是否有未跟踪的重要文件
- **区分 core 与 cloud**：确保 cloud 特定文件不会被添加到 local-core

### 2. 检查脚本

可以使用以下命令检查未被 Git 跟踪的 Python 文件：

```bash
# 检查所有未被跟踪的 Python 文件
find backend/app -name "*.py" -type f ! -name "__*" | while read f; do 
  git ls-files "$f" >/dev/null 2>&1 || echo "$f"
done

# 检查被代码引用的未跟踪文件
git status --porcelain backend/app | grep "^??" | grep "\.py$"
```

### 3. CI/CD 检查

建议在 CI/CD 中添加检查：
- 检查是否有未跟踪的 Python 文件被代码引用
- 验证 Docker 构建是否包含所有必需文件

### 4. 文档更新

- 更新 `.gitignore` 明确排除 cloud 特定目录
- 在开发文档中说明 volume mount 与 Git 跟踪的差异

---

## 相关提交

- `afb71db` - fix: 添加缺失的 runtime_environment.py 模型文件
- `b1375bb` - fix: 添加缺失的 control_knob.py 模型文件
- `60186f6` - fix: 添加 local-core 核心功能需要的模型文件
- `d57899d` - chore: 移除 cloud 特定的模型文件
- `03f59de` - fix: 添加缺失的 control_profile_store.py 文件
- `6073a6a` - fix: 添加缺失的 knob 相关服务文件
- `2cd1409` - fix: 修复 MindscapeProfile preferences 字段的 Pydantic 验证错误
- `d56b44a` - fix: 添加所有被代码引用的核心文件到 Git 跟踪
- `92f9a14` - fix: 修复 MindscapeProfile preferences 字段的 Pydantic 验证问题

---

## 总结

此次问题暴露了本地开发环境（volume mount）与生产环境（Git 跟踪）的差异。通过系统性的文件盘点和修复，确保了：

1. ✅ 所有核心功能文件都被 Git 跟踪
2. ✅ Cloud 特定文件被正确排除
3. ✅ 新环境可以正常构建和运行
4. ✅ 建立了预防措施和检查流程

**关键教训**：在本地开发时，即使文件未被 Git 跟踪也能正常工作（volume mount），但这会导致新环境出现问题。必须确保所有被代码引用的文件都被 Git 跟踪。

---

**最后更新**: 2026-01-06

