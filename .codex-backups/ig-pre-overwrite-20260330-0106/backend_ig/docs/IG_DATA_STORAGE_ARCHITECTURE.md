# IG Pack 数据存储架构说明

## 📋 当前数据存储机制

### 1. 数据持久化方式

IG Pack 的数据**确实会持久化存储**，当前采用**文件系统 + JSON 索引**的方式：

```
workspace/
├── artifacts/                    # Artifacts 存储目录
│   ├── artifacts_index.json      # 索引文件（快速查找）
│   └── {artifact_id}/            # 每个 artifact 的目录
│       └── artifact.json         # Artifact 数据（完整信息）
├── runs/                         # 执行记录存储目录
│   ├── runs_index.json           # 执行记录索引
│   └── {run_id}/                 # 每个执行的目录
│       ├── input.json            # 输入快照
│       ├── run.json              # 执行记录
│       └── steps/                # 步骤记录
└── vault/                        # Content Vault（Markdown 文件）
    └── ig_posts/                 # IG 贴文文件
        └── {post_path}.md        # 贴文内容（frontmatter + content）
```

### 2. 数据存储流程

#### Playbook 执行 → Artifact 创建

1. **Playbook 执行**：用户执行 playbook（如 `ig_post_generation`）
2. **Tool 输出**：Tool 返回结果数据
3. **Artifact 注册**：Control Plane Registry 调用 `register_artifact()`
4. **文件保存**：
   - 保存到 `artifacts/{artifact_id}/artifact.json`
   - 更新 `artifacts_index.json` 索引
5. **API 可访问**：通过 `/api/v1/workspaces/{workspace_id}/artifacts` 查询

#### 示例：生成贴文

```python
# 1. Playbook 执行
playbook: ig_post_generation
  ↓
# 2. Tool 生成内容
ig_post_generation_tool → {
  "text": "...",
  "hashtags": [...],
  "metadata": {...}
}
  ↓
# 3. Artifact 注册
registry.register_artifact(
  artifact_id="abc123",
  kind=ArtifactKind.DATA,
  content={...},
  metadata={...}
)
  ↓
# 4. 文件系统保存
artifacts/abc123/artifact.json  # 完整数据
artifacts_index.json            # 索引更新
  ↓
# 5. UI 读取
GET /api/v1/workspaces/{id}/artifacts?platform=instagram
```

### 3. 数据查询机制

#### 通过 API 查询

```typescript
// UI 端查询 artifacts
const response = await fetch(
  `${apiUrl}/api/v1/workspaces/${workspaceId}/artifacts?platform=instagram&include_content=true&limit=100`
);
const data = await response.json();
// data.artifacts = [{ id, content, metadata, ... }]
```

#### 索引机制

- **artifacts_index.json**：包含所有 artifact 的元数据（workspace_id, run_id, kind, created_at）
- **快速查找**：先查索引，再加载具体 artifact 文件
- **分页支持**：通过 limit/offset 参数控制

### 4. 内容产线支持

#### ✅ 数据持久化

- **Artifacts**：所有生成的贴文、审查记录、导出包都存储在文件系统中
- **执行记录**：所有 playbook 执行历史都保存
- **Content Vault**：贴文内容以 Markdown 文件形式存储在 vault 中

#### ✅ 数据可追溯

- **执行链**：通过 `run_id` 和 `execution_id` 可以追溯整个执行流程
- **变更历史**：通过 `changelog` 和 `decision_log` 可以查看审查历史
- **状态跟踪**：通过 `metadata.status` 可以跟踪贴文状态

#### ✅ 数据查询

- **列表查询**：通过 API 可以查询所有 artifacts
- **筛选查询**：支持按 platform、status、series_id 等筛选
- **关联查询**：通过 `series_id`、`arc_id` 可以关联查询

### 5. 当前架构的优势

1. **简单可靠**：文件系统存储，无需数据库配置
2. **易于备份**：整个 workspace 目录可以完整备份
3. **版本控制友好**：Markdown 文件可以纳入 Git 版本控制
4. **可扩展**：代码中已预留数据库迁移接口

### 6. 未来扩展性

#### 数据库迁移（可选）

代码中已有注释说明可以替换为数据库实现：

```python
# control_plane_registry.py:240
"""
this can be replaced with a database-backed implementation.
"""
```

如果未来需要更高性能，可以：
- 迁移到 PostgreSQL/MySQL
- 使用 ORM（如 SQLAlchemy）
- 保持 API 接口不变

### 7. 数据一致性保证

#### 文件系统层面

- **原子写入**：先写临时文件，再重命名（避免写入中断）
- **索引更新**：每次保存 artifact 时同步更新索引
- **错误处理**：写入失败时记录日志，不影响其他操作

#### 应用层面

- **状态管理**：通过 `metadata.status` 统一管理状态
- **写回机制**：Playbook 执行后通过 `register_artifact` 更新状态
- **冲突处理**：通过 `updated_at` 时间戳检测并发更新

## 🔄 内容产线数据流

### 完整流程示例

```
1. 生成贴文
   ig_post_generation → artifact (draft) → vault/ig_posts/post_001.md

2. 审查贴文
   ig_review_system → artifact.metadata.review_status → vault/ig_posts/post_001.md (frontmatter)

3. 验证准备度
   ig_frontmatter_validator → artifact.metadata.readiness_score → 更新 metadata

4. 导出包生成
   ig_export_pack_generator → artifact (export_pack) → artifacts/{id}/export_files/

5. 发布贴文
   ig_publish_content → artifact.metadata.status = 'published' → vault/ig_posts/post_001.md

6. 成效回填
   ig_metrics_backfill → artifact.metadata.metrics → vault/ig_posts/post_001.md (frontmatter)
```

### 数据查询路径

```
UI 查询
  ↓
API: /api/v1/workspaces/{id}/artifacts
  ↓
Control Plane Registry
  ↓
WorkspaceStorage
  ↓
文件系统: artifacts/{id}/artifact.json
  ↓
返回给 UI
```

## 📊 数据存储容量

### 当前限制

- **文件大小**：单个 artifact JSON 文件通常 < 1MB
- **索引大小**：artifacts_index.json 通常 < 10MB（1000+ artifacts）
- **总容量**：取决于文件系统容量

### 性能考虑

- **查询性能**：索引文件加载快，但大量数据时可能需要分页
- **写入性能**：文件系统写入通常足够快（< 10ms）
- **并发安全**：文件系统锁机制保证并发安全

## ✅ 总结

**IG Pack 的数据是持久化存储的**，采用文件系统 + JSON 索引的方式：

1. ✅ **数据不会丢失**：所有 artifacts 和执行记录都保存在文件系统中
2. ✅ **支持内容产线**：完整的数据流和状态管理
3. ✅ **可查询追溯**：通过 API 可以查询和追溯所有数据
4. ✅ **可扩展**：未来可以迁移到数据库（代码已预留接口）

当前架构已经**完全支持内容产线**，无需担心数据丢失问题。
