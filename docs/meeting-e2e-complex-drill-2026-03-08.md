# Meeting Engine E2E Complex Drill — 多工具跨階段場景

> **日期**: 2026-03-08
> **User Message**: 「調研十篇近期關於自律神經的前沿研究，並製作為 30 篇 ig post 貼文，要配圖」

---

## 1. 場景分析

這是一個**跨三個能力域**的複合任務：

| 階段 | 能力域 | 子任務 | 預期工具 |
|------|--------|--------|----------|
| Phase 1 | **Research** | 調研 10 篇前沿論文 | `frontier_research.fetch_academic`, `frontier_research.fetch_arxiv` |
| Phase 2 | **Content Drafting** | 將論文轉化為 30 篇 IG 貼文草稿 | `content_drafting.generate_draft`, `semantic_seeds.generate_suggestions` |
| Phase 3 | **Image Generation** | 為每篇貼文配圖 | `core_llm.generate` (image mode), 或外部圖片生成接口 |
| Phase 4 | **Publishing** | 發佈 / 排程 IG 貼文 | `ig.ig_publish_post`, `content_scheduler.cs_schedule_create` |
| Phase 5 | **QA / Review** | 內容審核、一致性檢查 | 會議 critic 層自動覆蓋 |

---

## 2. 預期五層會議處理流程

### Round 1 — 需求拆解

| Agent | 預期行為 |
|-------|----------|
| **Facilitator** | 確認議程目標：10 篇研究 × 3 篇貼文/論文 = 30 篇。定義品質標準（學術準確性、IG 適讀性、配圖風格） |
| **Planner** | 提出 3-5 phase 行動計畫：research → content synthesis → image gen → scheduling → QA |
| **Critic** | 質疑：「10 篇研究」的來源？PubMed/arXiv？時間範圍（近期 = 多近）？配圖風格未定義。30 篇內容品質如何保障 |

### Round 2 — 計畫細化

| Agent | 預期行為 |
|-------|----------|
| **Facilitator** | 整合 R1 反饋，聚焦到可執行方案 |
| **Planner** | 細化每個 phase：指定 tool_name、input_params、blocked_by 依賴鏈 |
| **Critic** | 確認依賴順序合理（Phase 2 必須等 Phase 1 完成才有素材），建議 batch 策略 |

### Round 3 — 收斂決議

| Agent | 預期行為 |
|-------|----------|
| **Facilitator** | 宣布收斂，產出最終決議 |
| **Planner** | 產出 final action items JSON（這是 executor 的輸入） |
| **Critic** | 最終 sign-off |

### Executor Turn — Action Items 產出

**預期 action items 結構**：

```json
[
  {
    "title": "Phase 1: 前沿研究調研",
    "tool_name": "frontier_research.fetch_academic",
    "input_params": {"topic": "自律神經", "count": 10, "period": "recent"},
    "blocked_by": []
  },
  {
    "title": "Phase 2: 內容生成",
    "tool_name": "content_drafting.generate_draft",
    "input_params": {"source": "phase_1_output", "count": 30, "format": "ig_post"},
    "blocked_by": [0]
  },
  {
    "title": "Phase 3: 配圖生成",
    "tool_name": "core_llm.generate",
    "input_params": {"type": "image", "count": 30, "style": "medical_infographic"},
    "blocked_by": [1]
  }
]
```

---

## 3. 驗證矩陣

**E2E 驗證項目**（Evidence-Based — 每項都必須有 runtime 證據）：

### 3.1 Tool RAG 階段

| # | 驗證項 | 成功標準 | 證據命令 |
|---|--------|----------|----------|
| R1 | RAG 為此 query 回傳 research 相關工具 | `frontier_research.*` 出現在 top-5 | `retrieve_relevant_tools("調研自律神經…")` |
| R2 | RAG 為此 query 回傳 content 工具 | `content_drafting.*` 或 `ig.ig_publish_post` 出現 | 同上但不同 query |
| R3 | RAG cache 非空 | `len(engine._rag_tool_cache) > 0` | 從 engine instance 取 |

### 3.2 Null-Tool Gate

| # | 驗證項 | 成功標準 | 證據來源 |
|---|--------|----------|----------|
| G1 | Gate 不觸發（因為 RAG cache 有工具） | 不進入 self-heal retry 迴圈 | log search: `null-tool gate triggered` |

### 3.3 MANDATORY Constraint

| # | 驗證項 | 成功標準 | 證據來源 |
|---|--------|----------|----------|
| M1 | MANDATORY 注入 executor prompt | prompt 包含 `MANDATORY` + tool list | 從 `_build_turn_prompt` 輸出取 |

### 3.4 Executor Output

| # | 驗證項 | 成功標準 | 證據來源 |
|---|--------|----------|----------|
| E1 | Executor JSON 未被截斷 | `finish_reason: STOP`（不是 `LENGTH`） | LLM debug log |
| E2 | Action items ≥ 2 | `len(session.action_items) >= 2` | DB query |
| E3 | 至少 1 個 item 有 `tool_name` | `any(item.tool_name for item)` | DB query |
| E4 | tool_name 語意正確 | 包含 `frontier_research.*` 或 `content_drafting.*` 或 `ig.*` | DB query |
| E5 | blocked_by 依賴鏈存在 | 至少 1 個 item 有 `blocked_by: [0]` 或類似 | DB query |

### 3.5 Session 完整性

| # | 驗證項 | 成功標準 |
|---|--------|----------|
| S1 | Session status = CLOSED | 正常收斂 |
| S2 | Round count ≥ 2 | 至少 2 輪討論 |
| S3 | Events 包含完整 lifecycle | meeting_start → agent_turns → decision_final → action_item → meeting_end |
| S4 | Minutes 已生成 | `session.minutes_md` 非空 |

---

## 4. 執行指令

```bash
docker exec mindscape-ai-local-core-backend python3 -c "
import asyncio, sys, logging
logging.basicConfig(level=logging.WARNING, stream=sys.stderr)

async def drill():
    from backend.app.services.stores.meeting_session_store import MeetingSessionStore
    from backend.app.models.meeting_session import MeetingSession
    from backend.app.services.orchestration.meeting import MeetingEngine
    from backend.app.services.mindscape_store import MindscapeStore

    WS = '39b9af54-8c47-4a74-8f49-1d6d4450a100'
    PROJECT = 'ig_account_analysis_20260228_143932_92704362'
    MSG = '調研十篇近期關於自律神經的前沿研究，並製作為 30 篇 ig post 貼文，要配圖'

    ss = MeetingSessionStore()
    session = MeetingSession.new(
        workspace_id=WS, project_id=PROJECT,
        meeting_type='general', max_rounds=3,
        agenda=['調研自律神經前沿研究', '製作 30 篇 IG 貼文', '配圖生成策略'],
    )
    session.start()
    ss.create(session)
    print(f'Session: {session.id}', flush=True)

    event_store = MindscapeStore()
    workspace = await event_store.get_workspace(WS)

    class SC:
        max_retries = 2
        max_errors = 5
        max_rounds = 3
    class RP:
        retry_strategy = 'exponential_backoff'
    class Profile:
        loop_budget = None
        stop_conditions = SC()
        recovery_policy = RP()

    try:
        engine = MeetingEngine(
            session=session, store=event_store, workspace=workspace,
            runtime_profile=Profile(), profile_id='default-user',
            thread_id=None, project_id=PROJECT,
        )
        await engine.run(user_message=MSG)
    except Exception as exc:
        print(f'Engine error: {type(exc).__name__}: {exc}', flush=True)

    final = ss.get_by_id(session.id) or session
    print(f'Status: {final.status}', flush=True)
    print(f'Rounds: {final.round_count}', flush=True)
    print(f'Items: {len(final.action_items)}', flush=True)
    for i, item in enumerate(final.action_items):
        tn = item.get('tool_name')
        pc = item.get('playbook_code')
        title = item.get('title', '?')[:60]
        bb = item.get('blocked_by')
        inp = str(item.get('input_params', ''))[:80]
        print(f'  [{i}] tool={tn} playbook={pc} blocked_by={bb}', flush=True)
        print(f'       title=\"{title}\"', flush=True)
        print(f'       input_params={inp}', flush=True)
    has_tool = any(item.get('tool_name') or item.get('playbook_code') for item in final.action_items)
    print(f'HAS_TOOL_ACTION={has_tool}', flush=True)

asyncio.run(drill())
"
```

---

## 5. 結果與差距分析

Session: `2694671f-8401-4a20-a16d-bfbeb105b43f`

### 5.1 實際結果

| 欄位 | 值 |
|------|-----|
| Status | CLOSED |
| Rounds | 3 |
| Action items | 3 |
| HAS\_TOOL\_ACTION | True ✅ |
| RAG\_CACHE\_LEN | **0** ❌ |
| Minutes | 1330 chars ✅ |

**Action Items：**

| # | tool\_name | title | blocked\_by | input\_params |
|---|-----------|-------|------------|--------------|
| 0 | **null** ❌ | 【準備】確保專家資源並進行品牌校準 | `[]` | null |
| 1 | `ig.ig_post_style_analyzer` | 【設計】建立視覺基礎設施 | `[]` | `{account_name: jai_tcmyoga}` |
| 2 | `ig.ig_fetch_posts` | 【執行】啟動首個內容衝刺週期 | `[0, 1]` | `{limit: 6, account_name: jai_tcmyoga}` |

**LLM 警告**：2 個 turn 出現 `finish_reason=2`（非 STOP），但 output\_tokens（1686, 1952）遠低於 max\_output\_tokens（4096）— 可能被 safety filter 或其他限制截斷。

### 5.2 驗證矩陣結果

| # | 驗證項 | 預期 | 實際 | 狀態 |
|---|--------|------|------|------|
| R1 | RAG 回傳 research 工具 | `frontier_research.*` | — | ⚠️ RAG cache 為空 |
| R2 | RAG 回傳 content 工具 | `content_drafting.*` | — | ⚠️ 同上 |
| R3 | RAG cache 非空 | `> 0` | **0** | ❌ FAIL |
| G1 | Gate 不觸發 | — | — | ⚠️ 無法確認（RAG 空） |
| M1 | MANDATORY 注入 | prompt 含 MANDATORY | — | ⚠️ 需 prompt 層驗證 |
| E1 | Executor JSON 未截斷 | `finish_reason=STOP` | `finish_reason=2` (2 turns) | ⚠️ PARTIAL |
| E2 | Action items ≥ 2 | ≥ 2 | 3 | ✅ PASS |
| E3 | 至少 1 個有 tool\_name | ≥ 1 | 2/3 | ✅ PASS |
| E4 | tool\_name 語意正確 | `frontier_research.*` | `ig.ig_post_style_analyzer`, `ig.ig_fetch_posts` | ⚠️ PARTIAL |
| E5 | blocked\_by 依賴鏈 | 存在 | `[0, 1]` on item 2 | ✅ PASS |
| S1 | Status = CLOSED | CLOSED | CLOSED | ✅ PASS |
| S2 | Rounds ≥ 2 | ≥ 2 | 3 | ✅ PASS |
| S3 | 完整 lifecycle events | 有 | 有 | ✅ PASS |
| S4 | Minutes 已生成 | 非空 | 1330 chars | ✅ PASS |

### 5.3 差距分析（追查修正 2026-03-08 08:00）

> **修正**: 初始分析中 Gap 1 的結論有誤。經過深入追查，RAG pre-fetch **正常運作**（20 tools cached），
> 但 E2E 腳本在 `run()` 呼叫前取樣 `_rag_tool_cache`，才導致看到 0。

#### 追查證據鏈

| 步驟 | 驗證命令 | 結果 |
|------|----------|------|
| 1 | `BEFORE_RUN RAG_CACHE` | 0（`run()` 尚未執行） |
| 2 | `AFTER_RUN RAG_CACHE` | **20**（`run()` 內 pre-fetch 成功） |
| 3 | TOOL bindings for workspace | 0（無 allowlist filter 介入） |
| 4 | `search_rrf('research academic papers')` | **`frontier_research.fetch_academic` ✅** |
| 5 | `search_rrf('調研自律神經前沿研究')` | **只回傳 `ig.*` ❌** |
| 6 | `sonic_embeddings` 中 tool\_id | 0 rows（tools embedded 在 pgvector 中） |
| 7 | Indexed models | `bge-m3` + `nomic-embed-text` |

#### 真正根因: 跨語言 Embedding 語意鴻溝

**`frontier_research.fetch_academic` 已 indexed**（英文 description），但中文 query「調研自律神經前沿研究」的 embedding 和英文 `fetch_academic` 語意距離太遠，排名掉出 top-20。

**`ig.*` 工具排名靠前**是因為安裝時（deploy-pack）其 manifest description 可能含有中文關鍵字，或工具名稱本身（「ig\_fetch\_posts」、「ig\_publish\_post」）和 query 中的「ig post」語意匹配。

#### Gap 1（P0）: 跨語言 RAG 召回失敗

**工具存在但召回不到** — `frontier_research.*` 在英文 query 下 top-1 命中，但在中文 query 下完全消失。

修復方向：
- **(a)** `_build_tool_query_from_context` 加入英文 query augmentation（translate key terms）
- **(b)** Tool index 時為 description 加入多語關鍵字（`fetch_academic → 學術研究調研`）
- **(c)** 增大 `top_k`（20 → 40）提高 recall

#### Gap 2（P1）: action item tool\_name 偏差

因為 RAG 只回傳 `ig.*`，LLM 被限制在 IG 工具裡選擇。選了 `ig.ig_post_style_analyzer`（風格分析）和 `ig.ig_fetch_posts`（抓取既有貼文）而不是 `frontier_research` / `content_drafting`。

**這是 Gap 1 的下游效應** — 修復 RAG 召回即可連帶修復。

#### Gap 3（P1）: item[0] 沒有 tool\_name

「確保專家資源」是抽象規劃步驟。如果 RAG 有回傳 `frontier_research.*`，LLM 應該會映射到具體工具。

#### Gap 4（P2）: finish\_reason=2

2 個 turn 被非 max\_tokens 原因截斷（可能 safety filter / thinking budget），暫不阻塞核心路徑。

### 5.4 修正後修復項

| 優先序 | 修復 | 說明 |
|--------|------|------|
| **P0** | **跨語言 query augmentation** | `_build_tool_query_from_context` 對中文 query 加入英文關鍵字翻譯；或拆分為多 query 聯合檢索 |
| **P0-alt** | **Tool description 多語化** | `index_tool()` 時在 description 中加入中文同義詞 |
| P1 | **增大 RAG top\_k** | 從 20 → 40 提高 recall，減少跨語言遺漏 |
| P2 | **finish\_reason 監控** | 加入 `finish_reason != STOP` 的 warning log |





**影響**: LLM 完全靠自身知識選擇 tool\_name，沒有 RAG 提供的工具候選清單。這導致：
- LLM 選了 `ig.ig_post_style_analyzer` 和 `ig.ig_fetch_posts`（它熟悉的 IG 工具）
- 完全跳過 `frontier_research.*` 和 `content_drafting.*`（因為 LLM 不知道它們存在）

**根因推測**: RAG pre-fetch 使用 `user_message` 或 `agenda` 作為 query，但可能因為 workspace 上沒有 TOOL 類型 bindings，pre-fetch 被 short-circuit 跳過了。需要確認 `_prefetch_rag_tools` 邏輯。

#### Gap 2（P1）: tool\_name 語意不匹配

**預期**: `frontier_research.fetch_academic`（調研）, `content_drafting.generate_draft`（製作貼文）
**實際**: `ig.ig_post_style_analyzer`（風格分析）, `ig.ig_fetch_posts`（抓取既有貼文）

LLM 理解了「IG 貼文」關鍵字但選錯了工具方向 — 因為沒有 RAG 提供正確工具清單。

#### Gap 3（P1）: item[0] 沒有 tool\_name

第一個 action item「確保專家資源」沒有 tool\_name，是一個抽象規劃步驟。在有 RAG + MANDATORY 的情境下，這應該被映射到 `frontier_research.fetch_academic`。

#### Gap 4（P2）: finish\_reason=2

2 個 turn 的 `finish_reason=2`（不是 `STOP=1`）表示回應可能被 safety filter 或其他限制截斷。雖然 output\_tokens（1686/1952）低於 4096，但不是 STOP。需要確認是否影響了 JSON 完整性。

#### Gap 5（P2）: 缺少 research 和 content 工具

整個 action items 只提到 IG 相關工具，完全缺少：
- 研究調研工具（`frontier_research.*`）
- 內容生成工具（`content_drafting.*`）
- 圖片生成工具（`core_llm.generate`）
- 排程工具（`content_scheduler.*`）

### 5.4 後續修復項

| 優先序 | 修復 | 說明 |
|--------|------|------|
| **P0** | **修復 RAG pre-fetch** | 確認 `_prefetch_rag_tools` 為何在這個 workspace 回傳空。可能是 workspace bindings check 阻擋了 RAG query |
| **P1** | **擴展 RAG query 策略** | 當前 RAG query 可能只用了 project\_id，需要也用 user\_message 關鍵字來檢索工具 |
| **P1** | **executor prompt 注入工具清單** | 即使 RAG 有回傳，需確認 MANDATORY constraint 有把完整工具清單注入 executor prompt |
| **P2** | **finish\_reason 監控** | 加入 finish\_reason != STOP 的 warning log 和可能的 retry |
