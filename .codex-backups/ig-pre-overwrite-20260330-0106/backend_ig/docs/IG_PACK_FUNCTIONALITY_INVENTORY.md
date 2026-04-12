# IG Pack 功能清单

**建立日期**: 2026-01-17
**版本**: 1.0.0
**目的**: 盘点 IG Pack 当前所有可用功能，用于产品化架构规划

---

## 📋 概览

IG Pack 提供完整的 Instagram 内容生成、管理和发布工作流能力。当前包含：

- **18 个 Playbooks**（工作流程）
- **19 个 Tools**（工具函数）
- **21 个 Services**（服务模块）
- **3 个 UI Components**（界面入口元件，见 `manifest.yaml:ui_components`）

---

## 📚 Playbooks（18个）

### 一、内容创建（Content Creation）

#### 1. `ig_post_generation`
- **功能**: 生成 Instagram 贴文
- **描述**: 从内容生成 IG 贴文，优化 IG 平台特性（字数限制、标签、语调等）
- **工具依赖**:
  - `core_llm.structured_extract` - 结构化提取主题
  - `ig_post_style_analyzer` - 分析贴文风格
  - `unsplash_search_photos` - 搜索图片
- **支持语系**: zh-TW, en
- **主要步骤**:
  - 提取主题
  - 分析风格（可选）
  - 搜索图片（可选）
  - 加载文件上下文（可选）
  - 向量搜索上下文（可选）
  - 生成 IG 贴文

#### 2. `ig_template_engine`
- **功能**: 模板引擎
- **描述**: 应用模板生成多个变体的 IG 贴文
- **工具依赖**: `ig_template_engine_tool`
- **支持语系**: zh-TW, en, ja
- **特性**: 支持轮播、Reel、Story 模板，不同风格调性和用途

#### 3. `ig_content_reuse`
- **功能**: 内容复用
- **描述**: 在不同 IG 格式间转换和复用内容
- **工具依赖**: `ig_content_reuse_tool`
- **支持语系**: zh-TW, en, ja
- **转换类型**:
  - 长文章 → 轮播
  - 轮播 → Reel
  - Reel → Stories

---

### 二、内容管理（Content Management）

#### 4. `ig_hashtag_manager`
- **功能**: Hashtag 管理
- **描述**: 管理 hashtag 分组并组合 IG 贴文的 hashtags
- **工具依赖**: `ig_hashtag_manager_tool`
- **支持语系**: zh-TW, en, ja
- **功能**:
  - 品牌固定分组
  - 主题分组
  - 活动分组
  - 屏蔽 hashtag 检查

#### 5. `ig_asset_manager`
- **功能**: 资产管理
- **描述**: 管理 IG Post 资产，包括命名验证、尺寸检查和格式验证
- **工具依赖**: `ig_asset_manager_tool`
- **支持语系**: zh-TW, en, ja
- **支持类型**: post, carousel, reel, story 资产

#### 6. `ig_series_manager`
- **功能**: 系列管理
- **描述**: 管理 IG Post 系列，包括创建、更新、查询和交叉引用
- **工具依赖**: `ig_series_manager_tool`
- **支持语系**: zh-TW, en, ja
- **功能**:
  - 系列进度跟踪
  - 贴文导航

#### 7. `ig_vault_structure_manager`
- **功能**: 工作区结构管理
- **描述**: 管理 IG Post 工作流的工作区结构
- **工具依赖**: `ig_vault_structure_tool`
- **支持语系**: zh-TW, en, ja
- **功能**:
  - 初始化
  - 验证
  - 内容扫描

---

### 三、内容工作流（Content Workflow）

#### 8. `ig_review_system`
- **功能**: 审查系统
- **描述**: 管理审查工作流，包括变更日志跟踪、审查备注和决策日志
- **工具依赖**: `ig_review_system_tool`
- **支持语系**: zh-TW, en, ja
- **功能**: 内容修订周期的审查跟踪

#### 9. `ig_interaction_templates`
- **功能**: 互动模板
- **描述**: 管理互动模板，包括常用评论回复、DM 脚本、语调切换和模板分类
- **工具依赖**: `ig_interaction_templates_tool`
- **支持语系**: zh-TW, en, ja
- **功能**: 客户参与的模板管理

#### 10. `ig_metrics_backfill`
- **功能**: 指标回填
- **描述**: 管理发布后指标，包括手动回填、数据分析和性能元素跟踪
- **工具依赖**: `ig_metrics_backfill_tool`
- **支持语系**: zh-TW, en, ja
- **功能**:
  - 手动回填
  - 数据分析
  - 系列聚合

#### 11. `ig_batch_processor`
- **功能**: 批次处理
- **描述**: 管理多个贴文的批次处理，包括验证、生成和导出操作
- **工具依赖**: `ig_batch_processor_tool`
- **支持语系**: zh-TW, en, ja

#### 12. `ig_complete_workflow`
- **功能**: 完整工作流
- **描述**: 编排多个 playbook 来执行端到端的 IG 贴文创建和管理工作流
- **工具依赖**: `ig_complete_workflow_tool`
- **支持语系**: zh-TW, en, ja
- **工作流类型**:
  - 执行工作流
  - 创建贴文工作流
  - 审查工作流

#### 13. `ig_content_checker`
- **功能**: 内容检查器
- **描述**: 检查 IG Post 内容的合规问题，包括医疗/投资声明、版权、个人数据和品牌语调
- **工具依赖**: `ig_content_checker_tool`
- **支持语系**: zh-TW, en, ja

#### 14. `ig_export_pack_generator`
- **功能**: 导出包生成器
- **描述**: 生成完整的 IG Post 导出包，包括 post.md、hashtags.txt、CTA 变体和检查清单
- **工具依赖**: `ig_export_pack_generator_tool`
- **支持语系**: zh-TW, en, ja

#### 15. `ig_frontmatter_validator`
- **功能**: Frontmatter 验证器
- **描述**: 根据 Unified Frontmatter Schema v2.0.0 验证 frontmatter 并计算准备度分数
- **工具依赖**: `ig_frontmatter_validator_tool`
- **支持语系**: zh-TW, en, ja

---

### 四、内容集成（Content Integration）

#### 16. `ig_sync_content`
- **功能**: 内容同步
- **描述**: 从 Instagram 拉取 posts/reels/stories 内容到本地 workspace
- **工具依赖**:
  - `ig.ig_fetch_posts`
  - `ig.ig_fetch_reels`
  - `ig.ig_fetch_stories`
- **支持语系**: zh-TW, en
- **前置要求**: 需在 site-hub 完成 OAuth 授权
- **功能**:
  - 拉取 posts、reels、stories
  - 自动下载媒体文件
  - 生成 metadata 并保存
  - 可选：触发 openseo pipeline

#### 17. `ig_publish_content`
- **功能**: 内容发布
- **描述**: 发布内容到 Instagram（photo/reel/carousel）
- **工具依赖**:
  - `ig.ig_validate_media`
  - `ig.ig_publish_post`
- **支持语系**: zh-TW, en
- **前置要求**: 需在 site-hub 完成 OAuth 授权
- **支持类型**:
  - Photo（支持延迟发布，最多 6 个月后）
  - Reel（不支持延迟发布）
  - Carousel（多张图片）
  - ⚠️ **不支持 Stories**（Graph API 限制）

---

### 五、内容分析（Content Analysis）

#### 18. `ig_analyze_following`
- **功能**: 追踪账号分析
- **描述**: 使用浏览器自动化提取 Instagram 追踪列表并分析账号页面
- **工具依赖**: `ig.ig_analyze_following`
- **支持语系**: zh-TW, en
- **技术要求**: 需要 Playwright 浏览器自动化支持
- **功能**:
  - 提取追踪列表
  - 自动滚动加载所有账号
  - 提取账号信息（用户名、显示名称、简介、头像、验证状态）
  - 访问每个账号页面进行统计分析（可选）
  - 生成分析摘要报告

##### 执行与可观测性（2026-01-19 落地）
- **进度 artifact**: 会持续写入 `ig_analyze_following_progress`（artifact `metadata.source`）
  - **stage**: `dialog_opened` / `initial_collect` / `scrolling` / `visiting_pages` / `completed` / `error`
  - **关键字段**:
    - `total_accounts`（当前已收集 accounts 数）
    - `page_index/page_total/current_account`（在 `visiting_pages` 阶段）
    - `updated_at`（UI 用于 stale 判定）
- **execution_id / trace_id 对齐**:
  - 进度 artifact 以 `trace_id` 关联；当 runtime 只传 `execution_id` 时，会以 `execution_id` 作为 trace fallback，避免 UI “stale 但其实在跑”。
- **卡住保护**:
  - 每个账号页分析有 hard timeout（默认 90s，可用环境变量 `IG_ACCOUNT_PAGE_TIMEOUT_SEC` 调整），避免 Playwright 无限等待导致进度停更。
- **滚动策略**:
  - IG “追踪中”列表为虚拟化列表时，单纯改 `scrollTop` 可能不会触发加载；已改为对列表容器持续发送 wheel/scroll 事件，并以 “新增账号数” 判定是否继续滚动（避免误判 reached_bottom）。

##### 运行时/Runner 约束（Local-Core）
- **IG Profile 锁**: 同一个 `user_data_dir` 同时只能跑一个 IG 自动化任务（避免浏览器 profile 冲突）。
  - 若执行长时间 `queued` 且 `runner_skip_reason=ig_profile_locked`，表示被锁挡住（通常是另一个任务或孤儿锁）。
  - Runner 会维护 `runner_locks`（含 TTL/renew），并具备 stale lock reaper。

---

## 🔧 Tools（19个）

### 内容创建工具

1. **`ig_post_style_analyzer`**
   - 分析 IG 贴文视觉风格
   - 生成设计建议
   - 输入：参考图片路径/URL，是否包含情绪分析

### 管理工具

2. **`ig_hashtag_manager_tool`**
   - 管理 hashtag 分组
   - 组合 hashtags
   - 支持品牌固定分组、主题分组、活动分组

3. **`ig_template_engine_tool`**
   - 应用模板生成 IG 贴文变体
   - 支持轮播、Reel、Story 模板

4. **`ig_asset_manager_tool`**
   - 管理 IG Post 资产
   - 命名验证、尺寸检查、格式验证

5. **`ig_series_manager_tool`**
   - 管理 IG Post 系列
   - 创建、更新、查询、交叉引用

6. **`ig_vault_structure_tool`**
   - 管理工作区结构
   - 初始化、验证、内容扫描

### 工作流工具

7. **`ig_review_system_tool`**
   - 管理审查工作流
   - 变更日志跟踪、审查备注、决策日志

8. **`ig_interaction_templates_tool`**
   - 管理互动模板
   - 评论回复、DM 脚本、语调切换

9. **`ig_metrics_backfill_tool`**
   - 管理发布后指标
   - 手动回填、数据分析、性能跟踪

10. **`ig_content_reuse_tool`**
    - 内容格式转换
    - 文章→轮播、轮播→Reel、Reel→Stories

11. **`ig_batch_processor_tool`**
    - 批次处理多个贴文
    - 验证、生成、导出

12. **`ig_complete_workflow_tool`**
    - 编排多个 playbook
    - 端到端工作流执行

13. **`ig_content_checker_tool`**
    - 检查内容合规性
    - 医疗/投资声明、版权、个人数据、品牌语调

14. **`ig_export_pack_generator_tool`**
    - 生成导出包
    - post.md、hashtags.txt、CTA 变体、检查清单

15. **`ig_frontmatter_validator_tool`**
    - 验证 frontmatter
    - Unified Frontmatter Schema v2.0.0
    - 计算准备度分数

### 集成工具

16. **`ig_fetch_posts`**
    - 从 Instagram 拉取 posts
    - 需要 channel_config_id

17. **`ig_fetch_reels`**
    - 从 Instagram 拉取 reels
    - 需要 channel_config_id

18. **`ig_fetch_stories`**
    - 从 Instagram 拉取 stories（24小时内）
    - 需要 channel_config_id

19. **`ig_validate_media`**
    - 验证媒体文件格式和大小限制
    - 用于 Instagram 发布

20. **`ig_publish_post`**
    - 发布内容到 Instagram
    - 支持 photo/reel/carousel
    - 需要 channel_config_id

21. **`ig_analyze_following`** ⭐ NEW
    - 提取 Instagram 追踪列表
    - 分析账号页面
    - 使用 Playwright 浏览器自动化

---

## 🛠️ Services（21个）

### 核心服务

1. **`instagram_api_client.py`**
   - Instagram Graph API 客户端
   - 速率限制、退避策略、app_secret_proof
   - 获取资料、媒体列表、发布内容

2. **`site_hub_client.py`**
   - Site-hub 客户端
   - 获取 access_token、app_secret、ig_business_account_id

3. **`workspace_storage.py`**
   - 工作区存储管理
   - 文件路径管理、存储后端抽象

### 功能服务

4. **`asset_manager.py`** - 资产管理服务
5. **`batch_processor.py`** - 批次处理服务
6. **`complete_workflow.py`** - 完整工作流服务
7. **`content_checker.py`** - 内容检查服务
8. **`content_reuse.py`** - 内容复用服务
9. **`export_pack_generator.py`** - 导出包生成服务
10. **`frontmatter_schema.py`** - Frontmatter 模式定义
11. **`frontmatter_validator.py`** - Frontmatter 验证服务
12. **`hashtag_manager.py`** - Hashtag 管理服务
13. **`interaction_templates.py`** - 互动模板服务
14. **`metrics_backfill.py`** - 指标回填服务
15. **`review_system.py`** - 审查系统服务
16. **`run_tracker.py`** - 运行跟踪服务
17. **`series_manager.py`** - 系列管理服务
18. **`template_engine.py`** - 模板引擎服务
19. **`vault_structure.py`** - 工作区结构服务
20. **`control_plane_registry.py`** - 控制平面注册表

---

## 🎨 UI Components（3个）

### 1. `IGWorkbenchPage`
- **路径**: `ui/IGWorkbench.tsx`
- **功能**: Unified IG Workbench (modules + content views + execution control)
- **路由**: （由 Workspaces extension/mount 决定）
- **关联 Playbooks**: `ig_*`（含 `ig_capture_account_snapshot`；详见 `manifest.yaml:437-456`）

### 2. `ig_posts_grid_view`
- **路径**: `ui/IGGridViewModal.tsx`
- **功能**: IG Posts Grid View 和 Timeline View
- **路由**: `/workspaces/{workspace_id}/ig-posts`
- **关联 Playbook**: `ig_post_generation`
- **显示内容**: 贴文网格视图、时间线视图

### 3. `ig_following_analyzer` ⭐ NEW
- **路径**: `ui/IGFollowingAnalyzer.tsx`
- **功能**: IG Following List Analyzer with real-time progress and background execution
- **路由**: `/workspaces/{workspace_id}/ig-following-analyzer`
- **关联 Playbook**: `ig_analyze_following`
- **特性**:
  - 实时执行进度（SSE + 轮询）
  - 背景执行支持
  - 进度显示
  - 结果展示（统计摘要、账号列表）
  - CSV 导出

---

## 📊 功能分类矩阵

| 分类 | Playbooks | Tools | Services | UI Components（入口元件總數，不按分類拆） |
|------|-----------|-------|----------|---------------|
| 内容创建 | 3 | 1 | 5 | - |
| 内容管理 | 4 | 5 | 6 | - |
| 内容工作流 | 7 | 8 | 7 | - |
| 内容集成 | 2 | 5 | 2 | - |
| 内容分析 | 1 | 1 | 1 | - |
| **总计** | **18** | **20** | **21** | **3** |

---

## 🔄 工作流依赖关系

### 核心工作流
```
ig_post_generation
  ├─ ig_template_engine (可选)
  ├─ ig_hashtag_manager (可选)
  ├─ ig_asset_manager (可选)
  └─ ig_series_manager (可选)
      │
      ├─ ig_content_checker
      ├─ ig_frontmatter_validator
      ├─ ig_review_system
      │   └─ ig_export_pack_generator
      └─ ig_publish_content (集成)
```

### 完整工作流
```
ig_complete_workflow
  ├─ ig_post_generation
  ├─ ig_content_checker
  ├─ ig_review_system
  └─ ig_publish_content
```

### 批次处理工作流
```
ig_batch_processor
  ├─ ig_post_generation (批次)
  ├─ ig_content_checker (批次)
  └─ ig_frontmatter_validator (批次)
```

---

## 📦 存储结构

```
workspace/
├── posts/          # IG 贴文内容
├── series/         # 系列管理
├── templates/      # 模板文件
└── config/         # 配置文件
```

---

## 🔗 外部依赖

### Required Dependencies
- 无（当前所有依赖都是可选的）

### Optional Dependencies
- **`project_sandbox_manager`** - 项目沙箱管理
- **`unsplash`** - 图片搜索（用于 `ig_post_generation`）
- **`sonic_space`** - 向量搜索（用于外部文档搜索）

### External Services
- **`site-hub`** - OAuth 授权管理（用于 `ig_sync_content`、`ig_publish_content`）
- **`Instagram Graph API`** - Instagram 官方 API（用于内容同步和发布）

---

## ⚙️ 技术要求

### 运行时依赖
- **Python**: 3.11+
- **Playwright**: >=1.40.0（用于 `ig_analyze_following`）
- **Pillow**: >=10.0.0（用于图片处理）
- **httpx**: 异步 HTTP 客户端
- **SQLAlchemy**: 数据库 ORM（通过 local-core）

### 浏览器自动化
- **Playwright Chromium**（用于 `ig_analyze_following`）
- 需要安装浏览器：`playwright install chromium`

---

## 📈 产品化待办事项

### 当前状态
- ✅ 18 个 Playbooks 已定义
- ✅ 20 个 Tools 已实现
- ✅ 21 个 Services 已实现
- ⚠️ **3 个 UI Components**（Workbench 已作为统一入口，但部分 playbook 仍缺闭环 UX）

### 缺失 / 不足的 UI（以「閉環 UX」为准）

由于 `IGWorkbenchPage` 已纳入统一入口，当前的主要缺口不再是「完全没有页面」，而是：

- `ig_asset_manager` / `ig_vault_structure_manager`：Workbench `assets` 模块仍为 placeholder，缺 AssetsPanel
- `ig_template_engine`：缺模板清单/套用闭环（仅有零散对话框元件）
- `ig_content_reuse`：缺内容转换专用 UI
- `ig_sync_content`：缺同步内容专用 UI（account 选取 + posts/reels/stories + 结果展示）
- `ig_complete_workflow`：缺 workflow 可视化与 preset UX
- `ig_batch_processor`：缺批次范围选取与结果摘要视图

专项目标与实现 TODO：`capabilities/ig/docs/todos/IG_MISSING_UI_PLAYBOOKS_IMPLEMENTATION_TODOS_2026-01-20.md`

### 建议的产品化方案

#### 方案 A: 统一 Workbench
创建统一的 **IG Workbench** 组件，整合所有功能：
- 左侧面板：Playbook 导航和分类
- 中央面板：当前活动的 Playbook 执行界面
- 右侧面板：历史记录和结果查看

#### 方案 B: 分类工作台
按功能分类创建多个工作台：
- **Content Creation Workbench** - 内容创建工作台
- **Content Management Workbench** - 内容管理工作台
- **Content Workflow Workbench** - 内容工作流工作台
- **Integration Workbench** - 集成工作台
- **Analysis Workbench** - 分析工作台

#### 方案 C: 混合方案
- 主 Workbench 作为入口，展示所有 Playbook
- 重点功能（如 `ig_post_generation`）使用专门的工作台
- 其他功能通过 Playbook 执行界面访问

---

## 📝 附录

### Playbook 执行模式

- **Conversational**: 对话式执行（大部分 Playbook）
- **Async**: 异步执行（支持背景执行）
- **Requires Human Approval**: 需要人工批准（如 `ig_publish_content`）

### 数据本地化策略

- **Local Only**: 用户个人数据、工作区存储
- **Cloud Allowed**: 媒体文件、内容元数据、参与度指标

### 支持的语系

- **zh-TW** (繁体中文): 17 个 Playbooks
- **en** (English): 18 个 Playbooks
- **ja** (日本語): 15 个 Playbooks

---

## 🔍 技术架构要点

1. **API 客户端**: 使用 `InstagramAPIClient` 调用 Instagram Graph API
2. **Token 管理**: 通过 `site-hub` 统一管理 OAuth 授权
3. **存储后端**: 支持本地存储和 Obsidian Vault
4. **浏览器自动化**: 使用 Playwright 进行页面分析和数据提取
5. **实时更新**: 支持 SSE 和轮询两种方式
6. **背景执行**: 支持异步执行模式，用户可关闭窗口

---

**文档创建日期**: 2026-01-17
**最后更新**: 2026-01-20
**维护者**: IG Pack 开发团队
