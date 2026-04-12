# Mindscape 内容产线架构规划

**文档日期**: 2026-01-20
**范围**: 跨 Pack 产品整合与未来扩展方向
**定位**: 本地优先的个人内容工厂（Local-first Personal Content Factory）

---

## 一、IG Pack Playbook UI 缺口盘点

### 1.1 已完成项目 ✅

| 优先级 | 项目 | 状态 | 实作落点 |
|--------|------|------|----------|
| P0 | 文档与真实状态对齐 | ✅ | `IG_PACK_FUNCTIONALITY_SUMMARY.md` |
| P1 | AssetsPanel（`ig_asset_manager` + `ig_vault_structure_manager`） | ✅ | `ui/modules/AssetsPanel.tsx` |
| P2 | Produce 面板重构（Generate/Template/Reuse/Hashtag 分页） | ✅ | `ui/modules/ProducePanel.tsx` |
| P2 | Content Reuse UI | ✅ | ProducePanel 内 Reuse 分页 |
| P3 | Sync Content UI | ✅ | `ui/modules/PublishPanel.tsx` Sync 子区块 |
| P4 | Batch Processor 范围选取与结果摘要 | ✅ | `WorkbenchExecutionPanel.tsx` |
| P4 | Complete Workflow preset/inputs UI | ✅ | `WorkbenchExecutionPanel.tsx` |

### 1.2 尚未完成项目 ⏳

| 项目 | 缺口说明 | 决策点 |
|------|----------|--------|
| **Template Engine 闭环** | 「对选中贴文套用模板」的闭环 UX | 需决定写回策略：覆写 vault 文件 vs 产生草稿 artifact |

### 1.3 结论

**UI 缺口基本补全**。剩余的 `ig_template_engine` 闭环是产品决策问题（非技术债），建议在实际使用中验证用户偏好后再定义。

---

## 二、现有 Pack 资产盘点

### 2.1 Pack 清单

| Pack | 核心功能 | Playbook 数 | 产品定位 |
|------|----------|-------------|----------|
| **ig** | IG 内容产线：生成、管理、审核、发布、Following 分析 | 18 | 单平台深度工作流 |
| **content** | 内容创作：drafting, editing, copywriting, YT script, Canva 简报 | 7 | 通用内容工厂 |
| **planning** | 规划：product/project breakdown, strategy, user story mapping | 7 | 项目元认知 |
| **mind_lens** | 视觉特征萃取、mood/narrative 分析 | - | 感知层基建 |
| **mindscape_book** | 官方书籍系列管理：素材收集、起草、进度追踪 | 3 | 内部使用 |
| **web_generation** | 网站生成：site spec → page assembly → deploy | 13 | 长内容载体 |
| **canva** | Canva 整合：模板、文字更新、导出 | - | 视觉设计桥梁 |
| **multi_media_studio** | 多媒体项目：timeline、tracks、GPU render | - | 影音后制 |

### 2.2 现有能力矩阵

```
┌─────────────────────────────────────────────────────────────────┐
│                        感知层 (Perception)                       │
│  ┌─────────────────┐  ┌─────────────────┐                       │
│  │   Mind Lens     │  │ Following       │                       │
│  │ 视觉特征萃取    │  │ Analyzer        │                       │
│  │ mood/narrative  │  │ 竞品/灵感追踪   │                       │
│  └────────┬────────┘  └────────┬────────┘                       │
│           │                    │                                 │
├───────────┼────────────────────┼─────────────────────────────────┤
│           ▼                    ▼                                 │
│                        规划层 (Planning)                         │
│  ┌─────────────────────────────────────────────────────────────┐│
│  │  Planning Pack: product breakdown / strategy / user story   ││
│  └─────────────────────────────────────────────────────────────┘│
│                              │                                   │
├──────────────────────────────┼───────────────────────────────────┤
│                              ▼                                   │
│                        生产层 (Production)                       │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐           │
│  │ Content Pack │  │   IG Pack    │  │ Mindscape    │           │
│  │ drafting     │  │ post gen     │  │ Book         │           │
│  │ copywriting  │  │ template     │  │ 书籍系列     │           │
│  │ YT script    │  │ series       │  │              │           │
│  └──────┬───────┘  └──────┬───────┘  └──────┬───────┘           │
│         │                 │                 │                    │
├─────────┼─────────────────┼─────────────────┼────────────────────┤
│         ▼                 ▼                 ▼                    │
│                        输出层 (Distribution)                     │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐           │
│  │ Canva Pack   │  │ IG Publish   │  │ Web Gen      │           │
│  │ 视觉设计     │  │ 社群发布     │  │ 网站部署     │           │
│  └──────────────┘  └──────────────┘  └──────────────┘           │
└─────────────────────────────────────────────────────────────────┘
```

---

## 三、产品定位与差异化

### 3.1 你不是什么

| 竞品类型 | 代表产品 | 为什么不做 |
|----------|----------|------------|
| 云端 Social Tool | Buffer, Hootsuite, Later | SaaS 基建、规模化、API 依赖、合规成本高 |
| Content Calendar | Notion Calendar, CoSchedule | 功能同质化、无差异护城河 |
| AI Writing SaaS | Jasper, Copy.ai | 纯生成、无工作流深度 |

### 3.2 你是什么

**本地优先的个人内容工厂（Local-first Personal Content Factory）**

核心叙事：

> 「在你的电脑上，用你自己的帐号登入，以你累积的品牌人格为基底，将一个想法变成跨平台的内容矩阵。」

差异化要素：

| 要素 | 说明 |
|------|------|
| **Local-first** | 资料在本地、session 在本地、隐私可控 |
| **Persona-driven** | Mind Lens + Following Analyzer 萃取的风格基因贯穿整条产线 |
| **Workflow-centric** | 不是「功能清单」而是「工作流串接」 |
| **Bonus not Core** | Following list 等 session-based 功能是 bonus，稳定产品方案不依赖它 |

---

## 四、现有 Pack 整合方案：完整内容产线

### 4.1 核心工作流路径

```
┌─────────────────────────────────────────────────────────────────────────┐
│                     PERSONA FOUNDATION（品牌人格基底）                   │
│  ┌─────────────────────────────────────────────────────────────────────┐│
│  │ Mind Lens 萃取          Following Analyzer 竞品追踪                 ││
│  │ ↓ 视觉风格 token        ↓ 内容风格参考                              ││
│  │ ↓ mood/narrative        ↓ hashtag 趋势                              ││
│  └─────────────────────────────────────────────────────────────────────┘│
└─────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                     CONTENT IDEATION（内容构思）                         │
│  Planning Pack: product_breakdown → 内容矩阵规划                        │
│  Planning Pack: strategy_planning → 主题/系列策略                       │
└─────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                     CONTENT PRODUCTION（内容生产）                       │
│                                                                         │
│  ┌─────────────┐    ┌─────────────┐    ┌─────────────┐                 │
│  │ Long-form   │    │ Short-form  │    │ Visual      │                 │
│  │             │    │             │    │             │                 │
│  │ Content:    │───▶│ IG Pack:    │───▶│ Canva:      │                 │
│  │ draft_      │    │ post_gen    │    │ presentation│                 │
│  │ article     │    │ template    │    │             │                 │
│  │             │    │ content_    │    │ Web Gen:    │                 │
│  │ YT Script   │    │ reuse       │    │ site_spec   │                 │
│  └─────────────┘    └─────────────┘    └─────────────┘                 │
│         │                  │                  │                         │
│         └──────────────────┼──────────────────┘                         │
│                            ▼                                            │
│                   Content Reuse 格式转换                                │
│                   长文 → 轮播 → Reel → Stories                          │
└─────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                     QUALITY GATE（品质闸门）                             │
│  IG Pack: content_checker（合规检查）                                   │
│  IG Pack: frontmatter_validator（就绪度评分）                           │
│  IG Pack: review_system（审核工作流）                                   │
└─────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                     DISTRIBUTION（分发输出）                             │
│                                                                         │
│  ┌─────────────┐    ┌─────────────┐    ┌─────────────┐                 │
│  │ IG Publish  │    │ Web Deploy  │    │ Canva Export│                 │
│  │ photo/reel/ │    │ GCP VM      │    │ PDF/PNG     │                 │
│  │ carousel    │    │ Divi slot   │    │             │                 │
│  └─────────────┘    └─────────────┘    └─────────────┘                 │
└─────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                     MEASUREMENT（效果回填）                              │
│  IG Pack: metrics_backfill（指标回填）                                  │
│  IG Pack: sync_content（同步已发布内容）                                │
└─────────────────────────────────────────────────────────────────────────┘
```

### 4.2 实际串接范例

#### 范例 A：从灵感到 IG 发布

```
1. Following Analyzer → 追踪 @competitor 的贴文风格
2. Mind Lens → 萃取其视觉 token（色调、构图、mood）
3. IG Post Generation → 以萃取的风格 token 为 prompt context 生成贴文
4. Hashtag Manager → 推荐 hashtags
5. Content Checker → 合规检查
6. Export Pack → 产出 post.md + hashtags.txt
7. Publish Content → 发布到 IG
```

#### 范例 B：从长文到跨平台内容矩阵

```
1. Content Drafting → 撰写一篇深度文章
2. Content Reuse → 长文 → IG 轮播（5 slides）
3. Content Reuse → 轮播 → Reel 脚本
4. YT Script Generation → 长文 → YouTube 影片脚本
5. Web Generation → 长文 → 网站页面
6. Canva Presentation → 长文 → 简报 PDF
```

---

## 五、建议新增 Pack：补齐产品叙事

### 5.1 优先级 P0：Persona Foundation（短期优先扩充 `brand_identity` + `mind_lens`，不立即新开 Persona pack）

**为什么需要**：目前 Mind Lens / Following Analyzer 产出的「风格基因」是零散的，需要一个可版本化、可追溯的 Persona Profile 作为所有内容产出的基底。

**短期落地策略（与工作站路线对齐）**：

- **优先落在 `brand_identity`**：把 persona 视为 Brand Lens 的一部分（MI/BI/VI + voice + 视觉 tokens），由 `mind_lens` 提供 evidence
- **不立即新开 Persona pack**：避免过早拆分导致契约与资料结构双维护；若中期出现「CIS（设计师主导）」与「创作者 persona（工作站主导）」明显分歧，再抽成独立 `persona` pack

**扩充范围（建议新增到 `brand_identity` 的 playbooks）**：

| Playbook | 功能 |
|----------|------|
| `persona_profile_builder` | 从 Mind Lens 萃取 + Following Analyzer（可选）+ 用户显性输入，合成 Persona Profile |
| `persona_style_guide` | 产出品牌风格指南（色彩、语调、禁忌词、视觉参考） |
| `persona_voice_tuner` | 微调内容语调（正式/casual、专业/亲切） |
| `persona_consistency_checker` | 检查内容是否符合 Persona 设定 |

**资料结构（artifact，建议 local-only）**：

```yaml
# persona_profile.yaml
persona_id: "my-brand"
display_name: "我的品牌"
created_at: "2026-01-20"

visual_identity:
  primary_colors: ["#0a0a2a", "#ffa0e0"]
  mood_keywords: ["minimal", "tech", "warm"]
  reference_accounts: ["@account1", "@account2"]
  mind_lens_extractions:
    - extraction_id: "abc123"
      features: { ... }

voice_identity:
  tone: "professional_friendly"
  language_style: "zh-TW_conversational"
  forbidden_words: ["震撼", "颠覆", "爆款"]
  signature_phrases: ["让我们聊聊...", "关键洞察是..."]

content_preferences:
  preferred_formats: ["carousel", "reel", "long-form"]
  posting_frequency: "3x_weekly"
  hashtag_strategy: "niche_first"
```

**与现有 Pack 整合**：

```
brand_identity (扩充后的 Persona Foundation)
    │
    ├──▶ IG Pack: post_generation（注入 persona context）
    ├──▶ Content Pack: copywriting（注入 voice identity）
    ├──▶ Web Gen: site_spec（注入 visual identity）
    └──▶ Canva Pack: template selection（匹配 mood/colors）
```

### 5.2 优先级 P1：Cross-platform Scheduler Pack（跨平台排程）

**为什么需要**：目前 IG Pack 只处理 IG 发布，但用户通常需要跨平台协调（IG + 网站 + Newsletter）。

**核心理念**：本地管理排程，可选性推送到各平台。

**功能范围**：

| Playbook | 功能 |
|----------|------|
| `schedule_content` | 将内容排入发布队列（本地 artifact） |
| `calendar_view` | 提供日历视图的排程概览 |
| `batch_schedule` | 批次排程（如：一周份的 IG posts） |
| `cross_platform_sync` | 同一内容排程到多平台（IG + Web + Newsletter） |

**与现有 Pack 整合**：

```
Scheduler Pack (新)
    │
    ├──▶ IG Pack: publish_content（触发发布）
    ├──▶ Web Gen: deploy（触发网站更新）
    └──▶ Newsletter Pack (未来): send（触发邮件发送）
```

### 5.3 优先级 P2：Content Intelligence Pack（内容情报）

**为什么需要**：Following Analyzer 目前只抓取清单和基本统计，缺乏深度分析。

**功能范围**：

| Playbook | 功能 |
|----------|------|
| `competitor_style_analysis` | 深度分析竞品帐号的内容风格（结合 Mind Lens） |
| `trending_topics_tracker` | 追踪特定 niche 的热门话题 |
| `content_gap_finder` | 找出竞品未覆盖但有需求的内容缺口 |
| `performance_pattern_analyzer` | 分析高互动内容的共同特征 |

**与现有 Pack 整合**：

```
Content Intelligence Pack (新)
    │
    ├──▶ IG Pack: Following Analyzer（数据来源）
    ├──▶ Mind Lens: feature extraction（视觉分析）
    └──▶ Planning Pack: strategy_planning（输入洞察）
```

### 5.4 优先级 P3：Newsletter Pack（电子报通路）

**为什么需要**：长内容除了网站，Newsletter 是另一个高价值通路。

**功能范围**：

| Playbook | 功能 |
|----------|------|
| `newsletter_draft` | 从长文内容转换为 Newsletter 格式 |
| `newsletter_schedule` | 排程发送 |
| `subscriber_segment` | 订阅者分群管理 |

**整合服务**：Substack API / Buttondown API / ConvertKit API

---

## 六、产品叙事：从功能到故事

### 6.1 核心 Value Proposition

> **「一个想法，多平台内容矩阵。在你的电脑上，用你的品牌人格。」**

### 6.2 用户旅程故事

**Persona: 独立创作者 Alice**

```
Day 1: 建立品牌人格
├─ 用 Mind Lens 萃取喜欢的帐号视觉风格
├─ 用 Following Analyzer 追踪 5 个灵感帐号
└─ brand_identity/persona_profile 合成 Alice's Brand Persona

Day 7: 规划内容矩阵
├─ Planning Pack: 规划「AI 设计趋势」系列
└─ 产出 12 篇内容的主题大纲

Day 14-30: 批次生产
├─ Content Pack: 撰写 3 篇深度文章
├─ IG Pack: 每篇文章转换为 3 个 IG 贴文（轮播 + Reel + Quote）
├─ Web Gen: 深度文章部署到个人网站
└─ Canva Pack: 产出配套视觉图

Day 31+: 持续发布
├─ Scheduler Pack: 排程未来 2 周的内容
├─ IG Pack: 自动发布
└─ Content Intelligence: 追踪表现，调整策略
```

### 6.3 差异化定位图

```
                    ┌─────────────────────────────────────┐
                    │         云端 SaaS 区域              │
                    │   Buffer / Hootsuite / Later        │
                    │   ✗ 你不在这里                      │
                    └─────────────────────────────────────┘

        本地化程度 ◀───────────────────────────────────────▶ 云端化程度

    ┌─────────────────────────────────────┐
    │      Mindscape 定位                 │
    │  「本地优先的个人内容工厂」         │
    │                                     │
    │  ✓ 资料本地、隐私可控              │
    │  ✓ Session-based 功能是 bonus      │
    │  ✓ 工作流深度而非功能广度          │
    │  ✓ Persona-driven 内容产出         │
    └─────────────────────────────────────┘

                    ┌─────────────────────────────────────┐
                    │         纯生成工具区域              │
                    │   Jasper / Copy.ai                  │
                    │   ✗ 你也不在这里                    │
                    └─────────────────────────────────────┘
```

---

## 七、实作路线建议

### Phase 1: 稳固现有（1-2 周）

- [ ] 完成 `ig_template_engine` 闭环决策并实作
- [ ] IG Pack 全面 dogfooding，收集 UX 痛点
- [ ] 补齐 Content Pack 与 IG Pack 的实际串接测试

### Phase 2: Persona 基建（2-3 周）

- [ ] Persona 路線定錨：短期擴充 `brand_identity` 承載 persona（如有明顯分歧再拆成獨立 Persona pack）
- [ ] 設計 `persona_profile.yaml` schema（以 `artifact_ref` 共享，不以檔案路徑耦合）
- [ ] 實作 `persona_profile_builder` playbook（建議落在 `brand_identity`）
- [ ] 將 Persona 注入現有內容產出 playbooks（IG post gen, copywriting），並同步更新 playbook spec inputs

### Phase 3: 排程与跨平台（2-3 周）

- [ ] 实作 Scheduler Pack 核心 playbooks
- [ ] 提供 Calendar View UI
- [ ] 串接 IG Publish 与 Web Deploy

### Phase 4: 内容情报（3-4 周）

- [ ] 实作 `competitor_style_analysis`（结合 Following Analyzer + Mind Lens）
- [ ] 实作 `content_gap_finder`
- [ ] 将洞察输出整合进 Planning Pack

---

## 八、附录：Pack 依赖关系图

```
                              ┌──────────────┐
                              │   system     │
                              │  (core LLM)  │
                              └──────┬───────┘
                                     │
              ┌──────────────────────┼──────────────────────┐
              │                      │                      │
              ▼                      ▼                      ▼
      ┌──────────────┐      ┌──────────────┐      ┌──────────────┐
      │  mind_lens   │      │   planning   │      │   content    │
      │  (感知层)    │      │   (规划层)   │      │   (生产层)   │
      └──────┬───────┘      └──────┬───────┘      └──────┬───────┘
             │                     │                     │
             │    ┌────────────────┼────────────────┐    │
             │    │                │                │    │
             ▼    ▼                ▼                ▼    ▼
      ┌──────────────────────────────────────────────────────┐
      │                         ig                           │
      │  (IG 内容产线: gen → review → export → publish)      │
      └──────────────────────────────────────────────────────┘
                                  │
              ┌───────────────────┼───────────────────┐
              │                   │                   │
              ▼                   ▼                   ▼
      ┌──────────────┐    ┌──────────────┐    ┌──────────────┐
      │    canva     │    │ web_generation│    │  (future)    │
      │  (视觉设计)  │    │  (网站部署)  │    │  newsletter  │
      └──────────────┘    └──────────────┘    └──────────────┘
```

---

## 九、產品化盤點與 TODO（工作站）

- `mindscape-ai-cloud/docs/architecture/todos/ig-content-factory-productization-todos-2026-01-20.md`

**文件路径**: `mindscape-ai-cloud/capabilities/ig/docs/MINDSCAPE_CONTENT_PIPELINE_ARCHITECTURE_2026-01-20.md`
