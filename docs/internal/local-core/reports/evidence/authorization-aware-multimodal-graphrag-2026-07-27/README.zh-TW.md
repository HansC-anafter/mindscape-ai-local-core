# Authorization-aware Multimodal GraphRAG Evidence Bundle

日期：2026-07-27

本目錄只保存可重跑或可核對的收據，不把 source-ready、port-ready、synthetic test 或健康端點升格成整體產品完成。

## 收據索引

- `live-vector-rls-receipt.json`：live vector migration、non-owner runtime role、RLS、session 與 rollback-only confidentiality gate。
- `runtime-activation-receipt.json`：backend/control/runner 的乾淨來源 commit、容器 ID、route、Tool RAG schema 與 lane 啟用收據。
- `cleanup-receipt.json`：本輪11個disposable vector DB的精確清理與live DB保留readback。
- `creative-studio-install-receipt.json`：Creative Studio exact artifact、durable install、execution activation與原路徑。
- `docker-verification-summary.json`：fresh DB、runner lane、frontend、pack contract與registry測試摘要。
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

## 分層判定

- Source：核心contracts、facades、module leaves、migrations、tests已實作。
- Runtime：vector role/RLS、backend/control與knowledge runner均已由`46795dc2`乾淨來源啟用，最後資源觀測通過。
- Pack：Creative Studio已啟用；IG clean committed source尚未可建置。
- Product：native image/video/audio retrieval仍為`not_admitted`；目前完成的是不衝突的additive multimodal port，不是原生多模態release。

因此核心安全與GraphRAG foundation可判定`PASS`，但在IG clean-source release、第二個真實pack canary、完整projection/graph資料生成與native media admission完成前，總控狀態仍不得標為`PASS`。
