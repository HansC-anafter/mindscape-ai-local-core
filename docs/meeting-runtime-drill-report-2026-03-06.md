# Meeting Runtime Drill Report (2026-03-06)

## 1. 目標
- 驗證「自救優先」改動是否在真實 runtime 生效：
  - Deterministic tool name canonicalization（裸名 -> `pack.tool`）
  - 一次 bounded LLM repair（僅 `TOOL_NOT_ALLOWED`）
  - 再次 policy gate 驗證後才允許 dispatch

## 2. 本次已上線改動
- `backend/app/services/orchestration/meeting/dispatch_policy_gate.py`
  - 新增 `_canonicalize_tool_name()`
  - 在 allowlist 檢查前先做 deterministic normalize
- `backend/app/services/orchestration/meeting/engine.py`
  - 新增 `_attempt_tool_name_self_heal()`
  - 在 `_dispatch_phases_to_workspaces()` 內加入 repair pass + re-check gate
- `backend/app/services/orchestration/meeting/_prompts.py`
  - fallback tool inventory 改成 canonical `pack.tool`
  - executor prompt 明確要求 `tool_name` 使用完整 namespace

## 3. 測試結果
- 在 backend container 執行：
  - `test_meeting_v6.py`
  - `test_meeting_dispatch.py`
  - `test_meeting_prompt_injection.py`
- 結果：`79 passed`，`0 failed`

## 4. 真實 runtime 演練（重點）

### 4.1 演練 session
- Workspace: `39b9af54-8c47-4a74-8f49-1d6d4450a100`
- Project: `ig_account_analysis_20260228_143932_92704362`
- New meeting session: `32a7b799-32ea-49c0-97ae-9ebd41423d5a`
- 最終狀態：`closed`, `round_count=3`, `ended_at=2026-03-06 05:30:11+00`

### 4.2 觀察到的結果
- 會議流程完整收斂（有 `meeting_end`, `message`, `state_vector_computed`）。
- 但 `action_items` 仍是 task 類項目，`tool_name=null`，沒有形成可執行 tool action。
- 本次 session 事件中未觀察到 `tool_name_self_heal` 事件。
- 會議內容內仍出現 `ig.ig_capture_account_snapshot` 失敗敘述。

### 4.3 Artifact/Execution 證據
- 該 session 相關 execution artifacts（`external_agent`）皆為：
  - `status=completed`
  - `tool_calls=[]`
  - `error=null`
- 代表此次會議內主要是 agent 文字回合產物，未形成有效工具調用鏈。

## 5. 直接工具層驗證（獨立於 meeting）

### 5.1 錯誤參數測試
- `POST /api/v1/tools/execute`
- `tool_name=ig.ig_capture_account_snapshot`
- arguments 使用 `account_handle`
- 回傳：`unexpected keyword argument 'account_handle'`
- 結論：tool 已 resolve 到執行函式，但參數名錯。

### 5.2 正確參數測試
- 同 endpoint，改 arguments 為：
  - `target_account_handle`
  - `workspace_id`
- 回傳：`success=true`，成功抓取 `jai_tcmyoga` profile/counts/raw 資料。
- 結論：**工具本體可執行，runtime tool path 正常。**

## 6. 結論
- 「會議層是否已保證不斷鏈」：**否，尚未保證**。
- 「工具層是否可真執行」：**是，可真執行**。
- 目前卡點已從「tool id 解析」前移到「meeting action 生產與參數契約」：
  - 會議可能仍收斂為純文字 task（未強制產出 tool/playbook action）
  - 即使有工具名，參數也可能不符合 tool schema

## 7. 建議後續修復（優先順序）
1. 增加 meeting 結案前 gate：若使用者要求「必須實際調用工具」，且無 tool/playbook action，禁止收斂，強制再生 executor 回合。
2. 在 action dispatch 前做 tool input schema 驗證與參數修正（最少做 key alias mapping，如 `account_handle -> target_account_handle`）。
3. 讓 meeting minutes 的「工具執行結果」只採信實際 execution/tool output，避免引用未驗證的文字敘述。
4. 補 runtime 監控指標：
   - `% sessions with non-empty tool_calls`
   - `% sessions ended with action_items(tool_name/playbook_code) == 0`
   - `% sessions with repair invoked / repair success`

---

## 8. 斷鏈根因分析（Evidence-Based，2026-03-06 補寫；2026-03-06 修正）

> 本節依 `evidence-based-reporting` skill 規範撰寫。每項主張均附實際查詢輸出或代碼行號。
>
> **修正說明（2026-03-06 20:28）**：初版 8.1 的主因推論「manifest fallback 為空 → prompt 缺 Available Tools」已被 runtime probe 推翻。正確的根因重新整理如下。

---

### 8.0 前提修正：工具清單確實存在於 executor prompt

**Evidence** — runtime probe（在 backend container 中直接呼叫 `_build_tool_inventory_block()`）：

> **Evidence**: `docker exec mindscape-ai-local-core-backend python3 -c "from backend.app.services.orchestration.meeting._prompts import MeetingPromptsMixin; ..."`
> ```
> line_count=215
> first_10_lines:
>   - course_production.voice_training_submit: voice_training_submit
>   - course_production.voice_training_status: voice_training_status
>   ...
> contains_ig_capture: True
> ```

**結論**：workspace `39b9af54` 在呼叫 `_build_tool_inventory_block()` 時，manifest fallback **確實回傳 215 行工具清單**，包含 `ig.ig_capture_account_snapshot`。初版根因「prompt 缺 Available Tools 區塊」**不成立**，已撤回。

---

### 8.1 根因一：Workspace 無 TOOL binding → policy gate fail-open（已確認，但不是空工具清單的原因）

**Evidence** — DB query，workspace_resource_bindings（workspace `39b9af54`）：

> **Evidence**: `docker exec mindscape-ai-local-core-postgres psql -U mindscape -d mindscape_core -c "SELECT resource_id, resource_type, overrides::text FROM workspace_resource_bindings WHERE workspace_id='39b9af54-8c47-4a74-8f49-1d6d4450a100' ORDER BY resource_type, resource_id;"`
> ```
>  resource_id | resource_type | overrides
> -------------+---------------+-----------
> (0 rows)
> ```

**Evidence** — 代碼，`dispatch_policy_gate.py:L160-L162`：

> **Evidence**: [`dispatch_policy_gate.py:L160-L162`](file:///Users/shock/Projects_local/workspace/mindscape-ai-local-core/backend/app/services/orchestration/meeting/dispatch_policy_gate.py#L160-L162)
> ```python
>         if not bindings:
>             return None  # fail-open: no TOOL bindings = no restriction
>         return {b.resource_id for b in bindings}
> ```

**結論**：無 TOOL binding 使 policy gate **fail-open**（不限制工具）。這是確認的事實，但它的影響是「任何 tool_name 都能通過 policy gate」而非「prompt 缺工具清單」。若 LLM 輸出了 tool_name，它會直通到 dispatch。

---

### 8.2 根因二（主因）：Executor prompt 無強制約束 → LLM 語義推斷「工具故障不該調用」

**Evidence A** — 代碼，`_prompts.py:L609-L625`（修正前的 executor 指令）：

> **Evidence**: [`_prompts.py:L609-L625`](file:///Users/shock/Projects_local/workspace/mindscape-ai-local-core/backend/app/services/orchestration/meeting/_prompts.py#L609-L625)
> ```python
>         return (
>             common + playbook_block
>             + "As executor, produce only JSON array with up to 3 action items. "
>             'Schema: [{"title":"...","tool_name":null,...}] '
>             "tool_name is for direct tool invocation without a playbook. "
>             "Use tool_name exactly as listed in Available Tools. "
>             ...
>         )
> ```

**Evidence B** — DB query，session action_items（session `32a7b799`）：

> **Evidence**: `docker exec mindscape-ai-local-core-postgres psql -U mindscape -d mindscape_core -c "SELECT action_items::text FROM meeting_sessions WHERE id='32a7b799-32ea-49c0-97ae-9ebd41423d5a';"`
> ```json
> [
>   {"title": "更新專案狀態為「進行中 (降級分析模式)」", "tool_name": null,
>    "playbook_code": null, "landing_status": "task_created"},
>   {"title": "確認 IG 工具集故障的技術任務已建立", "tool_name": null,
>    "playbook_code": null, "landing_status": "task_created"}
> ]
> ```

**無直接證據的說明**：session `32a7b799` 的 executor prompt 實際內容無 session-level log 可查（traces=[]）。因此「LLM 看到工具清單但選擇輸出 null」這一行為是基於 (a) runtime probe 確認工具清單存在、(b) action_items 全為 null 的結果已知，兩者之間的 LLM 行為屬**推論**，非直接實測。

**合理推論**：會議 agenda 含「IG 工具集執行異常」的討論；LLM 可能因語義判斷「工具目前故障，不適合在 action item 中調用」而輸出 null。同時，prompt 缺少**強制約束**（「Available Tools 非空時至少一個 action item 必須設定 tool_name 或 playbook_code」），LLM 無法被約束不走 null 路徑。

---

### 8.3 根因三：Self-heal 無法啟動（確認，原因不變）

**Evidence A** — action_items 全為 `task_created`（見 8.2 Evidence B）

**Evidence B** — 代碼，`engine.py:L636-L646`（self-heal 啟動條件）：

> **Evidence**: [`engine.py:L636-L646`](file:///Users/shock/Projects_local/workspace/mindscape-ai-local-core/backend/app/services/orchestration/meeting/engine.py#L636-L646)
> ```python
>             for idx, item in enumerate(action_items):
>                 if item.get("landing_status") != "policy_blocked":
>                     continue
>                 if item.get("policy_reason_code") != "TOOL_NOT_ALLOWED":
>                     continue
> ```

**Evidence C** — tasks table（同 session）：

> **Evidence**: `docker exec mindscape-ai-local-core-postgres psql -U mindscape -d mindscape_core -c "SELECT task_type, pack_id, status FROM tasks WHERE params::text LIKE '%32a7b799%';"`
> ```
>  task_type           | pack_id             | status
> ---------------------+---------------------+---------
>  meeting_action_item | meeting_action_item | pending
>  meeting_action_item | meeting_action_item | pending
> ```

**結論**：`tool_name=null` 的 item 不觸發 allowlist check → `landing_status=task_created`（非 `policy_blocked`）→ self-heal loop 掃描到 0 筆符合條件的項目，直接返回 0。這與 4.3 節「未觀察到 `tool_name_self_heal` 事件」完全一致。

---

### 8.4 修正後斷鏈路徑圖

```
用戶觸發 meeting session（議題：IG 工具集故障）
        │
        ▼
engine._build_tool_inventory_block()
  → workspace 無 TOOL binding（0 rows confirmed）
  → 走 manifest fallback → 回傳 215 行工具清單（confirmed）
  → executor prompt 包含 "=== Available Tools ===" 區塊（共 215 行）
        │
        ▼
executor LLM 接收：工具清單 215 行 + schema 範例 tool_name=null
  → 無強制約束（MANDATORY 缺席）
  → LLM 語義推斷（無直接 log 證據）→ 輸出 tool_name=null
        │
        ▼
_parse_action_items() 解析
  → action_items: tool_name=null（DB confirmed）
        │
        ▼
dispatch_policy_gate.check_dispatch_policy()
  → tool_name 為 null → 跳過 allowlist check（dispatch_policy_gate.py:L66）
  → landing_status = "task_created"（非 policy_blocked）
        │
        ▼
_attempt_tool_name_self_heal()
  → 掃描 policy_blocked items → 0 筆
  → 直接返回 0，self-heal 從未執行
        │
        ▼
會議結束，action_items 全為純文字 task，tool_calls=[] ✗
```

### 8.5 修復優先順序（基於修正後根因）

| 優先 | 根因 | 修復方向 | 狀態 |
|------|------|---------|------|
| P0 | 根因二（prompt 無強制約束） | Executor prompt 加入 MANDATORY 約束：工具清單非空時至少一個 action item 必須設定 tool_name 或 playbook_code | ✅ 已實施（`_prompts.py`） |
| P0 | 根因三（self-heal 盲點） | 新增 pre-dispatch null-tool gate：所有 action_items 都為 null 且工具清單非空時，觸發一次 executor re-generation | ✅ 已實施（`engine.py`） |
| P1 | 根因一（fail-open 無限制） | ~~為 workspace 建立 TOOL resource binding~~ → **改用 Tool RAG 動態裁切取代靜態 binding**（見 §9） | ✅ 已實施（`engine.py`, `_prompts.py`） |
| P2 | 可觀察性 | RAG pre-fetch 失敗 log 從 `debug` 升 `warning`；補 executor prompt 的 session-level log | ✅ 部分實施（log level 已升級） |

---

## 9. Tool RAG 動態裁切（2026-03-07 補寫）

### 9.0 架構決策：棄 binding、走 RAG

靜態 TOOL binding 對開放式 meeting 任務窗口**不可行**——meeting agenda 涵蓋的工具範圍無法事前預測。

正確解法是 **Tool RAG 動態裁切**：用 meeting 上下文（agenda + user_message + project_id）作為語意查詢，從全域工具池召回 top-K 候選，取代 215 行 manifest 全量灌入。

這與 OpenClaw 式的 policy-driven pruning（profile / allow-deny / agent role 先切小）是不同的擴展哲學：

- **OpenClaw 路線**：治理先行的白名單裁切，適用於「單一 agent、單一任務域、強控制」。
- **Tool RAG 路線**：檢索先行的候選縮圈，適用於「跨 workspace、跨 capability pack、開放任務窗口」。

本系統採後者。

### 9.1 已有路徑與修正

Meeting 引擎**已有 3-tier tool inventory**（bindings → RAG cache → manifest fallback），但 runtime 一直靜默 fallback 到 manifest。

**根因**：

| Gap | 問題 | 修正 |
|-----|------|------|
| A | `engine.py:L236` 呼叫 `retrieve_relevant_tools()` 缺 `workspace_id` | 補傳 `self.session.workspace_id` |
| B | RAG 失敗 log 為 `debug` level，正常環境完全看不見 | 升 `warning` |
| C | `_build_tool_query_from_context()` 缺 project context，query 品質不穩 | 加 `project_id` 補強 |

**Evidence** — commit `6088baa0`：

```
fix(meeting): wire Tool RAG pre-fetch with workspace_id and fix observability
```

### 9.2 修正（二）：null-tool gate 和 MANDATORY constraint 啟動條件

**問題**：P0 修正的兩個安全機制都僅依賴 `_has_workspace_tool_bindings()`：

- null-tool gate（`engine.py:L379`）：`if all_null and self._has_workspace_tool_bindings()`
- MANDATORY constraint（`_prompts.py:L709`）：`if has_explicit_bindings or playbooks_cache`

在 RAG-only workspace（無 TOOL binding），兩者均**永遠不觸發**——等於 P0 修正是死代碼。

**修正**：條件加入 `or bool(self._rag_tool_cache)`

```python
# engine.py — null-tool gate
has_tool_context = self._has_workspace_tool_bindings() or bool(
    getattr(self, "_rag_tool_cache", [])
)
if all_null and has_tool_context:

# _prompts.py — MANDATORY constraint
has_rag_tools = bool(getattr(self, "_rag_tool_cache", []))
if has_explicit_bindings or has_rag_tools or playbooks_cache:
```

---

## 10. 測試矩陣與驗證流程

### 10.1 自動化測試清單

所有測試在 Docker 容器內執行：

```bash
docker exec mindscape-ai-local-core-backend python3 -m pytest \
  /app/backend/tests/services/orchestration/test_meeting_v6.py \
  /app/backend/tests/services/orchestration/test_meeting_dispatch.py \
  /app/backend/tests/services/orchestration/test_meeting_prompt_injection.py \
  /app/backend/tests/test_meeting_null_tool_gate.py \
  -v --tb=short
```

| 測試檔 | 測試數 | 涵蓋修正 | 結果 |
|--------|--------|---------|------|
| `test_meeting_v6.py` | 48 | 引擎完整會議流程 | ✅ passed |
| `test_meeting_dispatch.py` | 7 | dispatch policy gate, self-heal, canonicalize | ✅ passed |
| `test_meeting_prompt_injection.py` | 24 | prompt 注入、workspace context、tool inventory | ✅ passed |
| `test_meeting_null_tool_gate.py` | 10 | null-tool gate、MANDATORY constraint、RAG cache | ✅ passed |
| **合計** | **89** | | **89 passed, 0 failed** |

### 10.2 各測試類別說明

**`TestNullToolGate`**（unit，不需 DB）：

- `test_gate_does_not_fire_without_explicit_bindings`：無 binding + 無 RAG → gate 不觸發
- `test_gate_fires_when_explicit_bindings_and_all_null`：有 binding + all null → gate 觸發
- `test_gate_does_not_fire_when_some_items_have_tool`：有 tool_name → 不觸發

**`TestMandatoryConstraintInjection`**（integration，需 Docker）：

- `test_no_mandatory_when_no_explicit_bindings`：無 binding + 無 RAG → MANDATORY 不注入
- `test_mandatory_present_when_explicit_bindings`：有 binding → MANDATORY 注入

**`TestRagCacheInjection`**（unit，不需 DB）：

- `test_retrieve_relevant_tools_returns_list`：RAG 回傳正確格式
- `test_rag_cache_hit_returns_same_object`：cache 命中回同一物件
- `test_different_workspace_different_result`：不同 workspace_id 使用獨立 cache slot

### 10.3 py_compile 驗證

```bash
python -m py_compile backend/app/services/orchestration/meeting/engine.py
python -m py_compile backend/app/services/orchestration/meeting/_prompts.py
```

結果：✅ 全過

### 10.4 進度追蹤

| 項目 | 說明 | 狀態 |
|------|------|------|
| RAG gate unit test | `test_gate_fires_when_rag_cache_and_all_null` + `test_gate_does_not_fire_when_no_bindings_no_rag` | ✅ |
| MANDATORY + RAG test | `test_mandatory_present_when_rag_cache`：無 binding 但有 RAG cache → MANDATORY 應注入 | ✅ |
| Runtime probe | Docker 容器中呼叫 `retrieve_relevant_tools()` + meeting-like agenda query | ✅ |
| E2E meeting session | 觸發真實 meeting，觀察 action_items 是否產出 `tool_name != null` | ⬜ |

### 10.5 Runtime Probe 結果（2026-03-07）

```bash
docker exec mindscape-ai-local-core-backend python3 -c "
import asyncio
from backend.app.services.tool_rag import retrieve_relevant_tools
async def probe():
    queries = [
        'IG account analysis and follower tracking',
        'schedule social media post for next week',
        'analyze target account following list',
    ]
    for q in queries:
        results = await retrieve_relevant_tools(q, top_k=5)
        print(f'Query: {q}')
        print(f'  Results: {len(results)} tools')
        for r in results[:3]:
            print(f'    - {r[\"tool_id\"]}: {r.get(\"display_name\",\"?\")}')
asyncio.run(probe())
"
```

**結果**：

| Query | Top-1 Tool | 語意匹配 |
|-------|-----------|---------|
| IG account analysis and follower tracking | `ig.ig_analyze_following` | ✅ 正確 |
| schedule social media post for next week | `content_scheduler.cs_calendar_view` | ✅ 正確 |
| analyze target account following list | `ig.ig_analyze_following` | ✅ 正確 |

每個 query 回傳 5 個候選，top-1 語意匹配正確。**確認 RAG pre-fetch 在 runtime 可正常工作**，不再靜默 fallback 到 manifest。

