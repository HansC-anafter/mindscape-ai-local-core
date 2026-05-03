# AOL Runtime Workbench 第一階段重構收尾查驗報告 - 2026-05-03

## 1. 結論

第一階段 P0 重構可以進入收尾驗收。八個 P0 大檔目標與後續暴露出的 Object Runtime service shim blocker 已降到 500 行以下；目前保留 route path、model import、frontend legacy export、backend route monkeypatch contract 與 command/graph contract。

> **Evidence**: `wc -l backend/app/services/object_runtime/*.py backend/app/routes/core/workspace/object_runtime.py backend/app/routes/core/workspace/meeting_graph.py 'web-console/src/app/workspaces/[workspaceId]/meetings/page.tsx' web-console/src/components/capabilities/meeting-workbench/AOLMeetingBottomShell.tsx web-console/src/components/capabilities/meeting-workbench/PropertiesInspector.tsx web-console/src/components/capabilities/aol-runtime-shell/AOLRuntimeShellProviderImpl.tsx`
> ```text
>        2 backend/app/services/object_runtime/__init__.py
>      418 backend/app/services/object_runtime/action_helpers.py
>      405 backend/app/services/object_runtime/action_service.py
>      340 backend/app/services/object_runtime/catalog_service.py
>      361 backend/app/services/object_runtime/common.py
>      139 backend/app/services/object_runtime/dependencies.py
>      447 backend/app/services/object_runtime/graph_service.py
>      459 backend/app/services/object_runtime/materialization_service.py
>      286 backend/app/services/object_runtime/meeting_attach_service.py
>      238 backend/app/services/object_runtime/meeting_projection.py
>      142 backend/app/services/object_runtime/route_services.py
>      272 backend/app/services/object_runtime/selection_service.py
>      249 backend/app/services/object_runtime/summary_service.py
>      366 backend/app/routes/core/workspace/object_runtime.py
>      137 backend/app/routes/core/workspace/meeting_graph.py
>      132 web-console/src/app/workspaces/[workspaceId]/meetings/page.tsx
>      378 web-console/src/components/capabilities/meeting-workbench/AOLMeetingBottomShell.tsx
>      238 web-console/src/components/capabilities/meeting-workbench/PropertiesInspector.tsx
>       90 web-console/src/components/capabilities/aol-runtime-shell/AOLRuntimeShellProviderImpl.tsx
>     5099 total
> ```

## 2. 路徑一致性

實作路徑與目前內部狀態文件一致：`refactor-milestone-status-2026-05-02.md` 已明確標記第一階段可關閉，並把 Object Runtime service shim 拆分列為 Checkpoint 32。

> **Evidence**: `rg -n "route_services.py|Checkpoint 32|可關閉|Object Runtime service line gate|Backend command and graph combined regression|Comment and internalization hygiene" docs-internal/implementation/aol-runtime-workbench-2026-05-02/refactor-milestone-status-2026-05-02.md`
> ```text
> 11:| 第一階段重構里程碑 | 完成八個 P0 local-core 檔案的相容優先拆分，保持 route path、frontend export、測試契約不破壞，並讓第二階段產品 UX 可以在穩定模組邊界上開展。 | 可關閉；八個 P0 目標與 Object Runtime service shim 均已拆到低於 500 行，route path、model import、frontend legacy export 與 backend monkeypatch contract 均保留。 |
> 415:### Checkpoint 32: 拆分 Object Runtime service shim
> 417:- `backend/app/services/object_runtime/route_services.py` 從 2874 行相容 shim 降到 142 行，只保留 compatibility facade、helper alias 同步與 endpoint delegation。
> 466:11. Object Runtime service line gate:
> 470:12. Backend command and graph combined regression:
> 474:13. Comment and internalization hygiene:
> ```

## 3. Contract Gates

Backend syntax gate 已通過。

> **Evidence**: `.venv/bin/python -m py_compile backend/app/services/object_runtime/*.py backend/app/routes/core/workspace/object_runtime.py backend/app/routes/core/workspace/meeting_graph.py backend/app/models/meeting_graph.py backend/app/models/object_runtime/__init__.py backend/app/models/object_runtime/actions.py backend/app/models/object_runtime/catalog.py backend/app/models/object_runtime/graph.py backend/app/models/object_runtime/instance_index.py backend/app/models/object_runtime/materialization.py backend/app/models/object_runtime/meeting.py backend/app/models/object_runtime/refs.py backend/app/models/object_runtime/selection.py backend/app/services/meeting_graph/projection_builder.py backend/app/services/meeting_graph/projection_utils.py backend/app/services/meeting_graph/task_projection.py backend/app/services/meeting_graph/event_projection.py`
> ```text
> exited with code 0
> ```

Object Runtime route/service contract 已通過。

> **Evidence**: `.venv/bin/python -m pytest backend/tests/object_action_planning_runtime_test.py backend/tests/object_instance_registry_runtime_test.py backend/tests/test_object_meeting_attachment.py backend/tests/test_aol_target_only_attach.py backend/tests/routes/core/test_workspace_object_runtime_api.py -q`
> ```text
> ..............................                                           [100%]
> 30 passed, 153 warnings in 2.13s
> ```

Meeting graph 與 command ledger backend contract 已通過。

> **Evidence**: `.venv/bin/python -m pytest backend/tests/meeting_execution_graph_object_semantics_test.py backend/tests/test_meeting_execution_graph_commands.py backend/tests/test_meeting_command_parser.py backend/tests/test_meeting_command_envelope.py backend/tests/test_meeting_command_status_sync.py -q`
> ```text
> ..................                                                       [100%]
> 18 passed, 153 warnings in 14.78s
> ```

Diff whitespace gate 已通過，僅有既有 PowerShell CRLF 提示。

> **Evidence**: `git diff --check`
> ```text
> warning: LF will be replaced by CRLF in install.ps1.
> warning: LF will be replaced by CRLF in scripts/setup.ps1.
> warning: LF will be replaced by CRLF in scripts/start.ps1.
> warning: LF will be replaced by CRLF in scripts/start_cli_bridge.ps1.
> exited with code 0
> ```

新增/改動的本輪目標程式碼路徑沒有中文註釋、TODO 或 FIXME。

> **Evidence**: `rg -n "TODO|FIXME|[\p{Han}]" backend/app/services/object_runtime backend/app/routes/core/workspace/object_runtime.py backend/app/models/object_runtime backend/app/routes/core/workspace/meeting_graph.py backend/app/services/meeting_graph 'web-console/src/app/workspaces/[workspaceId]/meetings'`
> ```text
> no matches; exited with code 1
> ```

## 4. 邊界與風險

本輪收尾沒有直接修改 VM，也沒有把 cloud capability source 當作 local-core runtime 來源。當前可見的目標檔案變更集中在 local-core route、models、services 與 web-console runtime/workbench shell。

> **Evidence**: `git status --short backend/app/services/object_runtime backend/app/routes/core/workspace/object_runtime.py backend/app/models/object_runtime backend/app/models/object_runtime.py backend/app/services/meeting_graph backend/app/routes/core/workspace/meeting_graph.py backend/app/models/meeting_graph.py 'web-console/src/app/workspaces/[workspaceId]/meetings' web-console/src/components/capabilities/meeting-workbench web-console/src/components/capabilities/aol-runtime-shell .gitignore`
> ```text
>  M .gitignore
>  D backend/app/models/object_runtime.py
>  M backend/app/routes/core/workspace/meeting_graph.py
>  M backend/app/routes/core/workspace/object_runtime.py
>  M web-console/src/app/workspaces/[workspaceId]/meetings/page.tsx
>  M web-console/src/components/capabilities/meeting-workbench/AOLMeetingBottomShell.spec.tsx
>  M web-console/src/components/capabilities/meeting-workbench/AOLMeetingBottomShell.tsx
> ?? backend/app/models/meeting_graph.py
> ?? backend/app/models/object_runtime/
> ?? backend/app/services/meeting_graph/
> ?? backend/app/services/object_runtime/
> ?? web-console/src/app/workspaces/[workspaceId]/meetings/MeetingRecordsHeader.tsx
> ?? web-console/src/app/workspaces/[workspaceId]/meetings/MeetingSessionCard.tsx
> ?? web-console/src/app/workspaces/[workspaceId]/meetings/MeetingSessionDetailPanel.tsx
> ?? web-console/src/app/workspaces/[workspaceId]/meetings/MeetingSessionList.tsx
> ?? web-console/src/app/workspaces/[workspaceId]/meetings/meetingRecords.types.ts
> ?? web-console/src/app/workspaces/[workspaceId]/meetings/meetingRecordsApi.ts
> ?? web-console/src/app/workspaces/[workspaceId]/meetings/meetingRecordsUtils.ts
> ?? web-console/src/components/capabilities/aol-runtime-shell/
> ?? web-console/src/components/capabilities/meeting-workbench/...
> ```

剩餘風險不是第一階段 line-count blocker，而是第二階段產品 UX gate：AOL Runtime Workbench 必須把 Context Bar、Object Outliner、Semantic Flow Canvas、Inspector、Command Dock/Ledger 與 AOL Session notification 串成使用者可理解的任務閉環。

## 5. 下一步

1. 以 `aol-runtime-workbench-product-ux-ui-layout-implementation-plan-2026-05-02.md` 為第二階段主計劃。
2. 下一個實作不得再以「拆檔」當里程碑，而要對齊產品 gate：使用者能從 focus/guidance/context 判斷下一步，並透過單一 Command Ledger 執行。
3. IG / PD 的 pack-specific guidance、review route、proposal semantics 只能透過 bounded projection、ObjectRef、command template 與 materializer contract 進入 local-core。
