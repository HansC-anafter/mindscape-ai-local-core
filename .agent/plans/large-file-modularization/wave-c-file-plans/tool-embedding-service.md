# Tool Embedding Service File Plan

Source file:
- `/Users/shock/Projects_local/workspace/mindscape-ai-local-core/backend/app/services/tool_embedding_service.py`

Parent plan:
- `/Users/shock/Projects_local/workspace/mindscape-ai-local-core/.agent/plans/large-file-modularization/local-core-implementation-modularization-plan-2026-03-23.md`

## Phase 1: Evidence Collection

- `:57` defines `ToolEmbeddingService`.
- `:60` starts `__init__()`.
- `:135` starts `_generate_embedding()`.
- `:159` starts `_generate_embedding_for_model()`.
- `:218` starts `ensure_table()`.
- `:1041` starts `index_all_tools_multimodel()`.
- `:1093` starts `_index_all_tools_for_model()`.
- `:1168` starts `reindex_all()`.
- Caller grep shows active compatibility usage: `tool_embedding_service` = 14.

## Phase 1.5: Historical Regression Analysis

- Commits `d243d82`, `1afb88d`, `56253af`, and `90d56e6` added embedding generation, multimodel indexing, registry integration, and reindex behavior here.
- The file now mixes provider calls, table management, and batch indexing orchestration.

## Phase 2: Problem Definition + Severity Scoring

1. **Embedding pipeline overload**: provider generation, model branching, table creation, batch indexing, and reindex control live together. Severity 4, Detection 4, Priority 16.
2. **Provider/store coupling**: embedding creation and DB writes are not cleanly separated. Severity 4, Detection 4, Priority 16.
3. **Batch-job fragility**: multimodel indexing changes can silently affect reindex behavior. Severity 4, Detection 3, Priority 12.

## Phase 3: Assumption Verification

- Assumption: the file can become a facade without changing callers.
  Verification: caller usage is on the module/service, not internal helpers.
- Assumption: embedding tests exist.
  Verification: `/Users/shock/Projects_local/workspace/mindscape-ai-local-core/backend/tests/test_tool_embedding_service.py`, `/Users/shock/Projects_local/workspace/mindscape-ai-local-core/backend/tests/test_tool_rag_cache.py`, and `/Users/shock/Projects_local/workspace/mindscape-ai-local-core/backend/tests/test_tool_rag_recall.py` exist.

## Phase 3.5: Pre-Mortem

- Model-specific embedding behavior drifts.
- Table bootstrap and batch indexing order change.
- Reindex path duplicates batch logic instead of reusing it.

## Phase 4: Plan Writing

Target package:
- `backend/app/services/embeddings/`

Modules to create:
- `service.py`
- `provider.py`
- `table_store.py`
- `multimodel_indexer.py`
- `reindex_job.py`

Implementation order:
1. Extract provider/model-specific embedding generation.
2. Extract table bootstrap and DB-write helpers.
3. Extract multimodel indexing orchestration.
4. Extract reindex entrypoint.
5. Leave the old file as a facade exporting `ToolEmbeddingService`.

Do-not-miss checklist:
- [ ] generation helpers moved
- [ ] table/bootstrap logic moved
- [ ] multimodel indexing moved
- [ ] reindex path moved
- [ ] old import path preserved

## Phase 5: Citation Audit

Re-verify before coding:
- `:57`
- `:60`
- `:135`
- `:159`
- `:218`
- `:1041`
- `:1093`
- `:1168`

## Phase 6: Validation SOP

```bash
pytest backend/tests/test_tool_embedding_service.py \
  backend/tests/test_tool_rag_cache.py \
  backend/tests/test_tool_rag_recall.py
```

## Phase 7: Evaluation & Automated Testing SOP

- Add a provider contract test before moving `_generate_embedding_for_model()`.
- Add a reindex regression test if extraction changes batch sequencing.
