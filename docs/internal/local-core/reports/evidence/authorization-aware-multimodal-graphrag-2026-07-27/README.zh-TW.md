# Authorization-aware Multimodal GraphRAG Evidence Bundle

日期：2026-07-27

本目錄只保存可重跑或可核對的收據。總控完成判定以 source、Docker、live index→query→revoke、資源非退化與產品 readback 的交集為準；native media 明確維持未准入，不能由 pointer、typed port 或健康端點升格。

## 收據索引

- `live-vector-rls-receipt.json`：live vector migration、non-owner runtime role、RLS、session 與 rollback-only confidentiality gate。
- `runtime-activation-receipt.json`：backend/control/runner 的乾淨來源 commit、容器 ID、route、Tool RAG schema 與 lane 啟用收據。
- `cleanup-receipt.json`：本輪20個disposable core/vector DB的精確清理與live DB保留readback。
- `creative-studio-install-receipt.json`：Creative Studio exact artifact、durable install、execution activation與原路徑。
- `docker-verification-summary.json`：fresh DB、runner lane、frontend、pack contract與registry測試摘要。
- `live-core-admission-projection-and-revoke-receipt.json`：IG 1.0.198、per-task admission、live graph projection、四路查詢、deny與revoke closure。
- `projection-registry-and-terminal-http-receipt.json`：projection-only startup registry、health/OpenAPI/product detail與terminal資源拓撲。
- `work-record-runtime-closure-receipt.json`：canonical report與Obsidian mirror的雙向frontmatter、content hash與`runtime_record_closed`驗證。
- `ig-clean-source-blocker.json`：IG clean committed source的manifest release blocker。
- `runtime-pressure-before-pack.json`：pack動作前資源快照。
- `runtime-pressure-before-knowledge-runner-reload.json`：未明示sole-owner時的正確拒絕。
- `runtime-pressure-approved-knowledge-runner-reload.json`：第一次受控knowledge runner重建前的PASS gate。
- `runtime-pressure-approved-knowledge-runner-reload-after-registry-fix.json`：registry修復後因受保護browser runner CPU超標而正確FAIL的gate。
- `runtime-pressure-approved-knowledge-runner-reload-after-load-drop.json`：負載下降後第一次runner重建的PASS gate。
- `runtime-pressure-approved-backend-reload.json`：第一次backend/control重建的PASS gate。
- `runtime-pressure-approved-backend-reload-after-tool-schema-fix.json`：`20260727041000`後第二次backend/control重建的PASS gate。
- `runtime-pressure-approved-clean-source-runner-reload.json`：knowledge runner切換到乾淨release worktree前的PASS gate。
- `runtime-pressure-post-activation.json`：最終啟用後的API、DB、PgBouncer與runner唯讀觀測。
- `runtime-pressure-post-admission-and-revoke-closure.json`：完成IG canary、revoke及Docker aggregate後的fixed-threshold三次PgBouncer terminal observation。
- `runtime-pressure-blocked-post-final-cleanup.json`：最終清理後首次後驗捕捉到Postgres CPU 268.99%並依固定200%門檻正確FAIL。
- `runtime-pressure-blocked-post-final-cleanup-contention.json`：相同門檻重跑捕捉到既有並行負載造成的endpoint timeout與PgBouncer等待，保留為不放寬門檻的阻斷證據。
- `runtime-pressure-post-cleanup-terminal.json`：等待既有負載自然回落後，以相同固定門檻通過；live DB、PgBouncer三次零等待與runner capacity保持健康。
- `terminal-post-cleanup-http-and-db-receipt.json`：最終Docker/curl與DB清理回讀；backend/control/frontend及revoke後resource detail皆為200，disposable GraphRAG DB為0。

## 分層判定

- Source：核心contracts、facades、module leaves、migrations、tests已實作。
- Runtime：vector role/RLS、backend/control與knowledge runner均由乾淨release worktree啟用；projection-only startup registry與最後資源觀測通過。
- Pack：Creative Studio已啟用；IG 1.0.198 exact artifact亦完成 durable install/activation，無backend/runner restart。
- Product：live IG canary完成1 record、3 entities、2 relations、1 community/report，authorized四路查詢各命中1、denied principal為0；revoke後四路與coverage皆為0，產品surface不暴露inactive derivatives。
- Multimodal：native image/video/audio retrieval仍為`not_admitted`；本輪完成的是不衝突的additive port與明確truth state，不是原生多模態release。

因此本總控的authorization-aware GraphRAG implementation與multimodal extension seam判定`PASS_WITH_EXPLICIT_NATIVE_MEDIA_NON_ADMISSION`。Native modality日後仍需各自model/index/hardware/quality admission；該後續能力不反向否定本輪已驗證的text/graph、安全與擴充介面。
