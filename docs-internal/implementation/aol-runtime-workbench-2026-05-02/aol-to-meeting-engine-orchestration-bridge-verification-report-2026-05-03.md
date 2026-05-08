# AOL 到 MeetingEngine 編排橋接 P0 查驗報告

日期：2026-05-03

## 2026-05-05 PD E2E Ledger Override

本報告若被用於 PD storyboard E2E 後續驗收，必須同時引用 `pd-storyboard-e2e-preflight-ledger-2026-05-05.md`。本報告的 bridge 方向查驗不等同於 real IG refs 高品質 storyboard 內容通過；正式 PD E2E 必須先證明 workspace executor 為 `codex_cli`、selected IG refs 為 real catalog refs、reference analysis 完成、cue map 非空、90s reels 為 45 scenes、逐鏡 LLM judge 與 visual scope gate 通過。

本報告依據 `evidence-based-reporting`、`evidence-based-planning` 與 `deploy-pack` 三個 skill 查驗。查驗範圍包含 local-core source code、cloud pack source code、內部實作計劃與外部官方 agent workflow / graph orchestration 文檔。本輪未查 live API、DB row、runtime logs，因此不宣稱目前 running instance 與 source code 狀態完全一致。

## 1. 結論

1. **路徑一致性：方向一致，但不是已落地狀態。** P0 計劃把 AOL command、object refs、graph guidance、relations、pack affordances 轉成 `HandoffIn` / request-contract metadata 並送入 `MeetingEngine.run()`，這與目前 local-core 已存在的 command ledger、HandoffIn、RequestContract、MeetingEngine 插槽方向一致。現況 code 仍是 `route_playbook` / `route_object_action` / `route_chat`，尚無 `route_meeting_orchestration` 或 `AOLMeetingOrchestrationBridge`。
2. **能否實現設計目標：能，但必須修訂幾個落地細節。** 概念上能達成「meeting graph node 作為 AI next-step guidance 與 tool-callable workflow spine」；但計劃中的 `RequestContract.metadata.addressable_object_layer`、`compiled_task_ir_id`、MeetingEngine 建構來源、既有 PD-specific handoff legacy 都必須補正，否則開工時會落到錯誤欄位或複製初始化邏輯。
3. **查漏補缺：存在 P0 級修訂項。** 最大問題不是方向錯，而是計劃還需要把「HandoffIn.metadata 如何 merge」、「TaskIR id 如何持久化」、「MeetingEngine factory 如何復用」、「現有 PD-specific HandoffIn normalizer 如何處理」寫成硬性修改項。
4. **外部主流環境：不脫節，且修正方向與主流一致。** LangGraph、OpenAI Agents SDK、AutoGen、CrewAI 的官方文檔都指向同一趨勢：由中心 orchestration / graph / session / flow 管理工具調度、狀態、human-in-the-loop、trace 與恢復。當前 direct dispatch 現況落後於這個方向；P0 bridge 計劃落地後才對齊。

## 2. Evidence

E1. `evidence-based-reporting` 要求 factual claim 先有證據，且 code behavior 需要檔案與行號。Source: `.agent/skills/evidence-based-reporting/SKILL.md:L8-L26`。

E2. `evidence-based-planning` 要求計劃先查真實 source，且輸出順序包含 Problem list、Evidence、Proposed changes、Verification SOP、Automated test plan、Risks / open questions。Source: `.agent/skills/evidence-based-planning/SKILL.md:L18-L39`。

E3. `deploy-pack` 要求 capability 從 cloud repo 打 `.mindpack`，經 local-core control plane install API 安裝，不得走錯 plane。Source: `/Users/shock/Projects_local/workspace/mindscape-ai-cloud/.agent/skills/deploy-pack/SKILL.md:L23-L67`。

E4. local-core developer guide 禁止在 local-core 實作 Cloud 業務功能與能力層 API，IG/社群媒體業務功能必須留在 source-side capability repository。Source: `docs-internal/DEVELOPER_GUIDE_MINDSCAPE_AI.md:L11-L39`。

E5. local-core developer guide 禁止 local-core 直接讀 cloud 檔案系統，允許 API、installer、NPM 包等標準分發方式。Source: `docs-internal/DEVELOPER_GUIDE_MINDSCAPE_AI.md:L54-L115`。

E6. Capability install guide 明確區分 release install 與 working-tree smoke deploy，且 local-core runtime 只允許讀已安裝 pack 與 installer 生成的 runtime alias。Source: `docs-internal/CAPABILITY_INSTALLATION_GUIDE.md:L24-L38`。

E7. 目前前端 command ledger 仍由 client 決定 dispatch mode：selected pack tool 走 `route_playbook`，兩個以上 object action entries 走 `route_object_action`，其他走 `route_chat`。Source: `web-console/src/components/capabilities/meeting-workbench/meetingCommandLedger.ts:L84-L91`。

E8. `route_object_action` 目前直接呼叫 object runtime plan/invoke。Source: `backend/app/services/meeting_command_dispatch.py:L38-L43`, `backend/app/services/meeting_command_dispatch.py:L61-L118`。

E9. `route_playbook` 目前直接呼叫 `orchestrator.handle_suggestion_action(action="execute_playbook")`。Source: `backend/app/services/meeting_command_dispatch.py:L140-L192`。

E10. command route 目前依序判斷 object action、playbook、chat，沒有 orchestration branch。Source: `backend/app/routes/core/workspace/meeting_commands.py:L155-L214`。

E11. full scope grep `backend web-console` 沒有找到 `route_meeting_orchestration`、`AOLMeetingOrchestrationBridge`、`dispatch_meeting_orchestration`、`should_route_meeting_orchestration`。Command: `rg -n "route_meeting_orchestration|AOLMeetingOrchestrationBridge|aol_meeting_orchestration|dispatch_meeting_orchestration|should_route_meeting_orchestration" backend web-console`。Output: no matches。

E12. `attach_objects_to_meeting()` 會建/取 MeetingSession、build handoff、在 target 與 context 同時存在時直接 materialize target outcome，並寫入 `session.metadata.addressable_object_layer`。Source: `backend/app/services/object_runtime/meeting_attach_service.py:L127-L260`。

E13. `HandoffIn` 已有 `playbook_requests`、`playbook_input_defaults`、`context_attachments` 與 `metadata`。Source: `backend/app/models/handoff.py:L263-L323`。

E14. `RequestContract` 目前有 `playbook_requests`、`playbook_input_defaults`、`workspace_scope`、`source_message`，但沒有 `metadata` 欄位。Source: `backend/app/models/request_contract.py:L49-L90`。

E15. `MeetingEngine.run()` 是七階段 pipeline，包含 contract compile、deliberation、action extraction、policy gate、dispatch、finalize。Source: `backend/app/services/orchestration/meeting/engine.py:L298-L330`。

E16. MeetingEngine 目前會把 `handoff_in.context_attachments`、`handoff_in.playbook_requests`、`handoff_in.playbook_input_defaults` merge 進 request-contract metadata；但 grep 未找到 `handoff_in.metadata` 被 merge 的使用。Source: `backend/app/services/orchestration/meeting/engine.py:L930-L1012`；Command: `rg -n "handoff_in\\.metadata|getattr\\(handoff_in, \\\"metadata\\\"|metadata = getattr\\(handoff_in" backend/app/services backend/app/models`。Output: no matches。

E17. `MeetingResult` 目前欄位是 `task_ir`，不是 `compiled_task_ir_id`。Source: `backend/app/services/orchestration/meeting/engine.py:L81-L92`。

E18. existing dispatch pipeline 回傳 `task_ir=compiled_ir`；handoff bundle service 用 `meeting_result.task_ir.task_id` 持久化並回傳 `task_ir_id`。Source: `backend/app/services/orchestration/meeting/_dispatch_pipeline.py:L349-L357`, `backend/app/services/handoff_bundle_service.py:L772-L790`。

E19. MeetingEngine constructor 需要 session、store、workspace、runtime_profile、profile_id、thread_id、execution_launcher、model、executor runtime、execution context 等；command route 目前只注入 workspace、orchestrator 與 stores。Source: `backend/app/services/orchestration/meeting/engine.py:L109-L123`, `backend/app/routes/core/workspace/meeting_commands.py:L104-L115`。

E20. 現有 pipeline 可建立 MeetingEngine 並呼叫 `MeetingEngine.run(message, handoff_in=handoff_in)`，且會 persist TaskIR。Source: `backend/app/services/conversation/pipeline_core.py:L330-L365`。

E21. 現有 handoff bundle intake 可經 MeetingEngine，並用 `meeting_result.task_ir.task_id` 持久化。Source: `backend/app/services/handoff_bundle_service.py:L772-L790`。

E22. 目前 HandoffIn model 內有 PD-specific `pd_storyboard_seed` 與 playbook route 推導，會選 `pd_scene_package_preview_handoff`、`pd_execute_storyboard_preview` 或 `pd_intake_storyboard_preview`。Source: `backend/app/models/handoff.py:L35-L79`, `backend/app/models/handoff.py:L106-L240`。

E23. IG installed pack guidance 目前在 local-core installed capability 中直接給 `recommended_pack = performance_direction` 與 `recommended_playbook = pd_director_guidance`。Source: `backend/app/capabilities/ig/services/object_layer/reference_runtime.py:L68-L99`。

E24. PD cloud source guidance 目前給 storyboard runtime guidance 與 `recommended_playbook = pd_scene_package_preview_handoff`。Source: `/Users/shock/Projects_local/workspace/mindscape-ai-cloud/capabilities/performance_direction/services/object_layer/storyboard_runtime.py:L328-L356`。

E25. 現有 frontend specs 仍期待 `route_playbook` 或 `route_object_action`。Source: `web-console/src/components/capabilities/meeting-workbench/AOLMeetingBottomShellDispatch.spec.tsx:L39-L46`, `web-console/src/components/capabilities/meeting-workbench/AOLMeetingBottomShellMentions.spec.tsx:L152-L165`, `web-console/src/components/capabilities/meeting-workbench/AOLMeetingBottomShellPackFixtures.spec.tsx:L80-L86`, `web-console/src/components/capabilities/meeting-workbench/meetingWorkbenchTestHarness.ts:L92-L102`。

E26. P0 bridge plan 已列出新增 `AOLMeetingOrchestrationBridge`、`route_meeting_orchestration`、default frontend routing、IG/PD E2E 驗收與自動測試。Source: `docs-internal/implementation/aol-runtime-workbench-2026-05-02/aol-to-meeting-engine-orchestration-bridge-implementation-plan-2026-05-03.md:L69-L178`, `docs-internal/implementation/aol-runtime-workbench-2026-05-02/aol-to-meeting-engine-orchestration-bridge-implementation-plan-2026-05-03.md:L180-L262`。

E27. milestone 文檔已把 AOL 到 MeetingEngine 編排橋接列為 blocker，並說未完成前 IG/PD E2E 只能算 smoke。Source: `docs-internal/implementation/aol-runtime-workbench-2026-05-02/refactor-milestone-status-2026-05-02.md:L5-L15`。

E28. LangGraph 官方文檔描述 durable execution 會保存 workflow progress，適用 human-in-the-loop、長任務、恢復；需要 persistence、thread identifier、把 side effects 包成 tasks。Source: https://docs.langchain.com/oss/javascript/langgraph/durable-execution L91-L102。

E29. LangGraph persistence 官方文檔說 graph state checkpoint 以 thread 組織，支持 human-in-the-loop、memory、time travel、fault tolerance。Source: https://docs.langchain.com/oss/python/langgraph/persistence L106-L117。

E30. OpenAI Agents SDK 官方文檔說 orchestration 決定 agents flow，可由 LLM 決策或由 code orchestrate；LLM 可用 tools 與 handoffs 來行動與委派。Source: https://openai.github.io/openai-agents-python/multi_agent/ L176-L205。

E31. OpenAI Agents SDK handoffs 官方文檔說 handoffs 讓 agent delegate tasks，並以 tool 形式呈現給 LLM。Source: https://openai.github.io/openai-agents-python/handoffs/ L180-L190。

E32. OpenAI Agents SDK HITL 官方文檔說工具可宣告 approval，run 結果以 interruption 暫停，RunState 可 serialize/resume。Source: https://openai.github.io/openai-agents-python/human_in_the_loop/ L184-L216。

E33. OpenAI Agents SDK tracing 官方文檔說 tracing 記錄 LLM generations、tool calls、handoffs、guardrails、custom events，並以 trace/spans 表示 workflow。Source: https://openai.github.io/openai-agents-python/tracing/ L190-L205。

E34. AutoGen AgentChat 官方文檔說 AgentChat 是 high-level multi-agent API，Advanced users 可用 autogen-core event-driven model；也列出 Selector Group Chat、Swarm、GraphFlow、Memory、Logging/Tracing。Source: https://microsoft.github.io/autogen/stable/user-guide/agentchat-user-guide/index.html L75-L124。

E35. CrewAI Flows 官方文檔說 Flows 支持 chain tasks、state management、event-driven architecture、conditional/loop/branching。Source: https://docs.crewai.com/en/concepts/flows L168-L171。

## 3. Findings

### F1. 與當前系統路徑一致，但不是已落地

P0 bridge 計劃的插入點正確：`meetingCommandLedger.ts` 是 default dispatch 決策點，`meeting_command_dispatch.py` 是 dispatch function 插入點，`meeting_commands.py` 是 route precedence 插入點，`HandoffIn` / `MeetingEngine.run()` 是既有 contract 與 engine entry。Evidence: E7-E16, E26。

不過目前 code 中完全沒有 bridge 實作與 route。這代表計劃是待開展，不是正在工作的已完成路徑。Evidence: E11。

### F2. 若按計劃落地，設計目標可達成，但需補四個硬修訂

可達成的原因：目前已有 durable command row、role-bearing object context、HandoffIn context attachments、RequestContract playbook directives、MeetingEngine seven-stage pipeline、TaskIR dispatch/result path。Evidence: E13-E21。

必補修訂：

1. `RequestContract.metadata.addressable_object_layer` 不是現有 model path。`RequestContract` 無 `metadata` 欄位；可選方案是新增 `metadata: Dict[str, Any]`，或明確寫成 `session.metadata["request_contract"]["addressable_object_layer"]` 並保證 `RequestContract.model_validate()` 不會丟失驗收需要的資料。Evidence: E14, E16。
2. `compiled_task_ir_id` 不是現有 `MeetingResult` 欄位。實作應使用 `meeting_result.task_ir.task_id`，並明確復用 `persist_meeting_task_ir` 或 `PostgresTaskIRStore.replace_task_ir()`。Evidence: E17-E21。
3. 需要 MeetingEngine factory / runner service。command route 目前沒有全部 constructor dependencies，直接在 route 裡 new `MeetingEngine` 會複製 pipeline_core/handoff_bundle_service 的初始化邏輯。Evidence: E19-E21。
4. 現有 HandoffIn 內有 PD-specific route normalizer。新 bridge 計劃要求不在 local-core 寫 pack-specific hard binding，因此必須標示該段為 legacy compatibility，並避免 P0 bridge 依賴它作為新主線。Evidence: E22。

### F3. 目前測試期待與新計劃衝突，必須先改測試契約

現有 frontend tests 明確期待 `route_playbook` 與 `route_object_action`。若直接改 production code 而不改 tests，測試會阻擋；若保留測試期待，計劃會被拉回 direct dispatch。Evidence: E25。

### F4. cloud/local-core 邊界方向合格，但要加一條實作紅線

P0 bridge 計劃把 bridge 放在 local-core host，且要求不 import IG/PD source repository、不直接讀 cloud 檔、不寫 IG/PD 業務邏輯，這符合 developer guide 與 deploy-pack。Evidence: E3-E6, E26。

缺一條紅線：若 IG/PD guidance schema、command templates、pack-owned materializer 需要改，必須在 `mindscape-ai-cloud/capabilities/{pack}` 改 source，打 `.mindpack` 並 install；不得直接改 `local-core/backend/app/capabilities/{pack}` 內已安裝 payload。Evidence: E3-E6。

### F5. 外部主流架構調研支持 P0 bridge 方向

主流官方文檔共同點：

- workflow 需要中心 orchestration / graph / flow，而不是 UI direct tool dispatch。Evidence: E28-E35。
- workflow state 要可持久化、可恢復、可 human-in-the-loop。Evidence: E28, E29, E32。
- tools / handoffs 是 orchestration engine 內的行為與 delegation，不應由 UI 卡片直接替代 orchestration。Evidence: E30, E31。
- trace / spans / events 是 workflow proof。Evidence: E33。

因此，P0 bridge 計劃不脫節；反而是目前 direct route-owned dispatch 現況與主流 durable workflow / orchestration pattern 不一致。

## 4. Required Amendments Before Implementation

1. **把 contract carrier 寫清楚**
   - 在計劃 Change 2 / Change 4 增列：
     - `HandoffIn.context_attachments` 必須承載 role-bearing AOL refs、graph guidance、relations、review routes。
     - `HandoffIn.metadata.addressable_object_layer` 若要使用，必須同步修改 `MeetingEngine._merge_request_contract_metadata()`，把 `handoff_in.metadata` merge 到 `session.metadata["request_contract"]`。
     - 若不改 `RequestContract` model，驗收不得寫 `RequestContract.metadata.addressable_object_layer`，而要寫 `session.metadata["request_contract"]["addressable_object_layer"]` 或 `context_attachments[].addressable_object_layer`。

2. **修正 TaskIR 欄位名稱**
   - 把計劃中的 `compiled_task_ir_id` 改成 `task_ir_id = meeting_result.task_ir.task_id`。
   - 明確要求 persist TaskIR，復用 `persist_meeting_task_ir` 或 `PostgresTaskIRStore.replace_task_ir()`。

3. **新增 MeetingEngine runner/factory**
   - 建議先新增 `backend/app/services/orchestration/meeting/meeting_engine_runner.py` 或同等 service。
   - 由 command dispatch 與既有 pipeline/handoff bundle 共用初始化方式，避免三套 MeetingEngine constructor。

4. **把 PD-specific HandoffIn normalizer 標為 legacy debt**
   - P0 bridge 不得依賴 `_build_pd_storyboard_playbook_request()` 作為新主路徑。
   - 後續應把 PD-specific seed 推導搬回 pack-owned guidance / playbook request producer，local-core 只吃 generic `playbook_requests`。

5. **明確區分 explicit override 與 guidance-selected tool**
   - 目前 `selectedPackTool` 直接導致 `route_playbook`。新計劃要定義：
     - user 明確點 run exact playbook：`route_playbook`
     - guidance command template / `@pack` mention / selected graph guidance：`route_meeting_orchestration`
   - frontend tests 必須覆蓋兩者，否則會再次滑回 direct playbook。

6. **補 runtime verification 前置條件**
   - 計劃中的 IG/PD E2E API check 必須先定義測試資料來源：已安裝 pack、可解析 IG refs、PD storyboard target、workspace/meeting ids。
   - 未有 live API/DB/log 證據前，不得把 source-code test pass 宣稱為 running runtime E2E。

## 5. Answer To Requested Questions

### 5.1 根據實作規劃，跟當前系統是否路徑一致？

一致，但要修訂細節。插入點與現有架構吻合：command ledger、meeting command route、HandoffIn、RequestContract merge、MeetingEngine.run、TaskIR persistence 都已存在。Evidence: E7-E21。

不一致處是「計劃名稱已存在、程式未存在」與「若照原文字實作會碰到錯誤欄位」：`route_meeting_orchestration` / `AOLMeetingOrchestrationBridge` 還沒實作；`RequestContract.metadata` 不是現有 model 欄位；`compiled_task_ir_id` 不是現有 MeetingResult 欄位。Evidence: E11, E14, E17。

### 5.2 如果落地這個實作，能否實現設計目標？

能，但必須按 Required Amendments 修訂後落地。成功條件不是產生 artifact，而是證明：

```text
MeetingCommandEnvelope
-> route_meeting_orchestration
-> AOLMeetingOrchestrationBridge
-> HandoffIn / request-contract metadata
-> MeetingEngine.run()
-> ActionIntent / TaskIR / dispatch_result
-> artifacts / proposals / review routes
-> graph + Command Ledger + AOL session notification
```

若只保留 direct object action 或 direct playbook，即使有 output，也不能算達成原始設計目標。Evidence: E7-E12, E15-E18, E26-E27。

### 5.3 查漏補缺：是否與 repo 現況不符、疏漏、錯誤？

有。需修：

1. `RequestContract.metadata.addressable_object_layer` 表述不符 repo 現況。Evidence: E14, E16。
2. `compiled_task_ir_id` 表述不符 repo 現況。Evidence: E17-E18。
3. 缺 MeetingEngine factory / runner insertion plan。Evidence: E19-E21。
4. 未處理現有 PD-specific HandoffIn normalizer 與新原則衝突。Evidence: E22。
5. 現有 tests 仍期待 direct dispatch，必須同步更新。Evidence: E25。
6. live runtime 驗證前置資料未定義；目前計劃已有 runtime evidence gap，但需要升級成 P0 驗收前置條件。Evidence: E26。

### 5.4 是否與當前主流網路社區環境脫節？

P0 bridge 計劃不脫節；目前 direct dispatch 現況脫節。

外部官方文檔顯示主流方向是：

- graph / workflow state durable checkpoint、thread、resume、HITL。Evidence: E28, E29。
- orchestration engine 決定 tool use / handoff / specialist delegation。Evidence: E30, E31。
- human approval / interruption / resume 是 run-level 行為。Evidence: E32。
- trace/spans 記錄 workflow、tool calls、handoffs。Evidence: E33。
- multi-agent frameworks 提供 centralized selector、directed graph workflow、event-driven flows 與 state management。Evidence: E34, E35。

因此，把 AOL Runtime Shell 改成 `AOL object refs + graph guidance + command intent -> MeetingEngine -> TaskIR/dispatch/provenance` 是與主流一致；讓 UI/pack guidance 直接 route playbook 或 object materializer 才是不一致。

## 6. Go / No-Go

**Go with amendments.**

開工前必須先修訂 P0 計劃，至少補上：

1. request-contract carrier 的正確欄位與 merge 實作。
2. TaskIR id/persistence 的正確欄位。
3. MeetingEngine runner/factory。
4. PD-specific HandoffIn normalizer legacy 處置。
5. explicit override vs guidance orchestration 的 frontend/backend 判定。
6. live runtime E2E 前置資料與 DB/API/log 驗收。

未完成這六項前，不應宣稱 IG/PD pack 接線 E2E 或 meeting-led workflow 完成。
