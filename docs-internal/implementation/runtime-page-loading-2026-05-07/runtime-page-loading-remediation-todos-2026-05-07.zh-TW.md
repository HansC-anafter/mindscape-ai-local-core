# Runtime 頁面載入修復實作計劃

最後更新：2026-05-07

## 不降級死線

- 禁止降低 inflight、queue partition、runner resource class、agent dispatch 能力。
- 禁止關閉 OCR、LLM、vector、object index、runner-browser、runner-vision。
- 禁止用手動 restart/stop/kill 當作效能修復；若 install response 要求 restart，必須等安全窗口或另行確認。
- 所有修復必須保留原資料與功能，只移除同步阻塞、重複請求、無界等待、錯誤健康檢查語意。

## 問題清單與優先級

1. **P1：`ig/post-thumbnail` 無界長尾阻塞頁面**
   Severity 5，Detection 4，Priority 20。證據：frontend proxy 253s/312s/372s 404。

2. **P2：IG run log counts 仍有秒級查詢**
   Severity 4，Detection 3，Priority 12。證據：`sidebar-counts` 1.9s-4.8s。

3. **P3：PD workbench 首屏仍受 Next dev compile 與 API waterfall 影響**
   Severity 4，Detection 3，Priority 12。證據：`/performance_direction/start` 7.6s-10.7s、frontend compile 10.9s/4.7s。

4. **P4：capability migration branch labels 缺失造成 branch-scoped migration warning**
   Severity 3，Detection 3，Priority 9。證據：install warning `Migration 20260124170000... has no branch_labels`。

5. **P5：local-core admission deferred index migration source 與 DB revision 狀態未完全對齊**
   Severity 3，Detection 4，Priority 12。證據：DB `alembic_version` 未見 `20260507063000`，但 live indexes 已存在。

## 已完成項目

1. `/healthz` 真 liveness：已用 source test 與 curl 驗證。
   不降級理由：readiness 被移到 `/health` / workspace health，能力檢查沒有消失。

2. OCR optional disabled：已用 unit tests 驗證不 probe。
   不降級理由：required mode 仍 probe；optional 未開時才回 disabled。

3. IG persistence batch writes：已打包安裝。
   不降級理由：寫入資料不減，僅減 DB round trips。

4. Installer pending-only migration fallback：已通過測試並在 IG install response 中看到 applied ancestry warning。
   不降級理由：pending revision 仍會跑，只避免重播已套用 revision。

5. `progress-snapshot` offload：已通過 local-core 測試。
   不降級理由：response contract 保持，避免 event loop 被同步 DB/JSON work 卡住。

6. IG workbench `sidebar-summary`：已打包安裝，IG pack active。
   不降級理由：counts 與 execution list 同時保留，只合併首屏請求。

7. `ig/post-thumbnail` bounded foreground fetch：cloud source 已提交 `5886e72`、pack 已安裝、validation succeeded。
   不降級理由：browser/post-detail fallback 保留為背景 cache refresh；前景 request 不再等待慢 fallback。

## 下一步實作順序

1. **Bounded thumbnail path activation**
   - 目前 source、pack、container disk 已完成；control API 8220 已在 3.173s 內回 404/queued。
   - backend API 8200 仍是舊載入 module，8s probe timeout；install response 已標示 active workloads `meeting_sessions=113`，所以不得手動 restart/kill。
   - reload 前置驗證目前 `valid:false`：既有 `brand_identity` / `expert_network` pack manifest 指到不存在的 API 檔，需先另案修正或明確批准 force reload。
   - 下一步只能在安全窗口執行 reload/activation，或等 active workloads 降到允許自動 reload；不得用停止任務或降 inflight 來換取啟用。
   - 驗證：reload 後重測 8200 與 8300 frontend proxy，`post-thumbnail` miss 必須在 bounded time 內返回，背景 cache refresh 仍排程。

2. **Counts path 收斂**
   - 檢查 `load_reference_counts` live reconciliation 與 `ig_reference_catalog` count snapshot。
   - 優先把 live overlay 做 bounded batch / cache key，而不是減少計數內容。
   - 驗證：`sidebar-summary` under load p95 低於 500ms；counts 與 active execution 顯示一致。

3. **PD workbench waterfall 盤點**
   - 從 `/capabilities/performance_direction/start`、capability host、workspace layout、WorkspaceDataContext 逐項列出首屏 API。
   - 合併只讀狀態、避免首屏重複 health/cloud-sync/status。
   - 不關 workspace health，不停 sync，只調整首屏併發與快取。
   - 驗證：fresh dev compile 與 warm route 分開記錄；warm route 目標 < 2s。

4. **Migration branch label 清理**
   - 只在 cloud IG migration source 處理 branch_labels，不直接改 local-core installed copy。
   - 驗證：重新 package 後 branch-scoped migration 不再出現無 branch label warning。

5. **`20260507063000` DB revision 對齊**
   - 先查 migration file、DB index、`alembic_version`、orchestrator ancestry。
   - 只有在證明 indexes 已存在且 revision 只需 stamp 時，才提出 stamp 計劃；不得盲目 apply/drop/recreate。

## 驗證 SOP

1. Unit / source tests：local-core health/OCR/installer/progress snapshot；cloud IG workbench/persistence。
2. Runtime API：`/healthz`、`/health`、`sidebar-summary`、`progress-snapshot`、PD start route。
3. Docker：`docker stats --no-stream`、runner-browser `docker top`、backend/control/frontend logs。
4. DB：`pg_stat_activity`、`pg_locks`、target indexes、running/pending task query。
5. Pack：package sha、install response、capability list `ig` activation/validation。

## 備查命令

```bash
/Users/shock/Projects_local/workspace/mindscape-ai-local-core/.venv/bin/python -m pytest backend/tests/healthz_liveness_spec.py backend/tests/system_health_checker_readiness_isolation_spec.py backend/tests/test_ocr_client_optional.py backend/tests/system_health_checker_ollama_spec.py backend/tests/runtime_assets_installer_migrations_spec.py backend/tests/progress_snapshot_thread_offload_spec.py -q
```

```bash
/Users/shock/Projects_local/workspace/mindscape-ai-local-core/.venv/bin/python -m pytest capabilities/ig/tests/workbench_api_test.py capabilities/ig/tests/persistence_seed_count_test.py capabilities/ig/tests/ig_seed_summary_fast_path_spec.py -q
```

```bash
curl -sS -o /dev/null -w '%{http_code},%{time_total}' "http://localhost:8200/api/v1/ig/workbench/sidebar-summary?workspace_id=bac7ce63-e768-454d-96f3-3a00e8e1df69&playbook_code_prefix=ig_&active_limit=100&status=running&status=queued&status=pending&status=paused&status=failed"
```
