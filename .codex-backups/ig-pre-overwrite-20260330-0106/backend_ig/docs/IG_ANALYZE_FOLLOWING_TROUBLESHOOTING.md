# IG Following Account Analysis Troubleshooting Log

## Problem Description

**Issue:** IG Following Account Analysis playbook returns `"Execution completed (conversation mode, no structured output)"` even though the playbook is configured with `execution_mode: "workflow"` in the playbook spec.

**Expected Behavior:**
- Playbook should execute in workflow mode
- Result should contain `step_outputs` with analysis data (`summary`, `accounts`, `metadata`)
- Frontend should receive structured output for display

**Actual Behavior:**
- API endpoint `/api/v1/playbooks/execute/{execution_id}/result` returns conversation mode completion message
- No `workflow_result`, `step_outputs`, or `outputs` in task `execution_context`
- Frontend cannot parse and display results

## Timeline

### 2025-01-05

#### Initial Issue
- Playbook spec has `execution_profile.execution_mode: "workflow"` in `ig_analyze_following.json`
- Playbook execution starts successfully (returns `execution_id`)
- Result endpoint returns conversation mode message instead of workflow result

#### First Investigation
**Root Cause Hypothesis:**
1. Result endpoint checks `playbook_runner.get_playbook_execution_result()` first
2. This method returns conversation mode message when execution_id not in `active_conversations`
3. Workflow mode result stored in `task.execution_context` is never checked

**Code Location:**
- `/api/v1/playbooks/execute/{execution_id}/result` endpoint
- File: `mindscape-ai-local-core/backend/app/routes/core/playbook_execution.py`

#### Fix Attempt #1
**Change:** Reordered result retrieval logic to check `task.execution_context` first before falling back to conversation mode.

**Code Changes:**
```python
# Before: Check playbook_runner first, then task execution_context
# After: Check task execution_context first, then playbook_runner
```

**Result:** Still returns conversation mode message.

#### Fix Attempt #2
**Change:** Added explicit check for task status (failed/running) before falling back to conversation mode.

**Code Changes:**
- Check if task exists
- If task status is `failed`, return 500 error instead of falling back
- If task status is not `completed/succeeded`, return 404 instead of falling back
- Only fall back to conversation mode if task doesn't exist

**Result:** Still returns conversation mode message, suggesting task is not being found or has no execution_context.

#### Current Investigation
**Test Results:**
```bash
# Execution starts successfully
Execution ID: 19db2855-5585-4e4c-9537-ecf30da72b35
Status: completed

# Result endpoint returns
{"status":"completed","execution_id":"19db2855-5585-4e4c-9537-ecf30da72b35","note":"Execution completed (conversation mode, no structured output)"}

# Checking task in database
curl "http://localhost:8200/api/v1/workspaces/{workspace_id}/executions?playbook_code=ig_analyze_following&limit=5"
# Result: execution_id not found in returned executions
```

**Key Findings:**
1. Execution ID is returned from start endpoint
2. Execution appears to complete (status: completed)
3. Task/execution record is not found in executions API
4. Result endpoint falls back to conversation mode because task is not found

## Code Flow Analysis

### Execution Start Flow
1. **API Endpoint:** `POST /api/v1/playbooks/execute/start`
   - File: `mindscape-ai-local-core/backend/app/routes/core/playbook_execution.py:start_playbook_execution()`
   - Calls `playbook_executor.execute_playbook_run()`

2. **Playbook Executor:**
   - File: `mindscape-ai-local-core/backend/app/services/playbook_run_executor.py`
   - `execute_playbook_run()` → `_handle_standalone()` or `_handle_plan_node()`
   - Checks `execution_mode == 'workflow'` and `playbook_run.playbook_json` exists
   - Routes to `_execute_workflow_standalone()` → `_execute_workflow_legacy()`

3. **Workflow Legacy Execution:**
   - File: `mindscape-ai-local-core/backend/app/services/playbook_run_executor.py:_execute_workflow_legacy()`
   - Creates `Task` with `execution_context`
   - Calls `workflow_orchestrator.execute_workflow()`
   - On success, updates task with `workflow_result`, `step_outputs`, `outputs` in `execution_context`
   - On failure, updates task with error in `execution_context`

### Result Retrieval Flow
1. **API Endpoint:** `GET /api/v1/playbooks/execute/{execution_id}/result`
   - File: `mindscape-ai-local-core/backend/app/routes/core/playbook_execution.py:get_playbook_result()`
   - **Current Logic:**
     - Try to get task from `TasksStore` by `execution_id`
     - If task exists:
       - Check `execution_context.workflow_result`
       - Check `execution_context.result`
       - Check `execution_context.step_outputs`
     - If task not found or no result, fall back to `playbook_runner.get_playbook_execution_result()`
     - `playbook_runner` returns conversation mode message if execution_id not in `active_conversations`

## Hypothesis

### Hypothesis 1: Task Not Created
- **Theory:** Workflow execution fails before task is created
- **Evidence:** Task not found in database queries
- **Next Step:** Check if `_execute_workflow_legacy()` is actually being called

### Hypothesis 2: Task Created But Execution Context Not Updated
- **Theory:** Task created, but `workflow_result` not saved to `execution_context`
- **Evidence:** Task may exist but `execution_context` empty or missing `workflow_result`
- **Next Step:** Check task creation and update logic in `_execute_workflow_legacy()`

### Hypothesis 3: Execution Path Issue
- **Theory:** Execution is not taking workflow path despite `execution_mode: "workflow"`
- **Evidence:** Result endpoint returns conversation mode, suggesting conversation execution
- **Next Step:** Verify `playbook_run.get_execution_mode()` returns `"workflow"` and `playbook_run.has_json()` returns `True`

### Hypothesis 4: Task Lookup Failure
- **Theory:** Task exists but `TasksStore.get_task_by_execution_id()` fails to find it
- **Evidence:** Task creation happens in `_execute_workflow_legacy()`, but lookup in result endpoint fails
- **Next Step:** Check `TasksStore` implementation and verify `execution_id` matches

## Next Steps

1. **Add Debug Logging:**
   - Log in `_execute_workflow_legacy()` when task is created
   - Log in `get_playbook_result()` when task lookup fails
   - Log execution mode determination in `execute_playbook_run()`

2. **Verify Execution Path:**
   - Confirm playbook is loaded correctly with `execution_mode: "workflow"`
   - Confirm `playbook_run.get_execution_mode()` returns `"workflow"`
   - Confirm `playbook_run.has_json()` returns `True`

3. **Check Task Storage:**
   - Verify task is actually created in database
   - Verify `execution_id` matches between creation and lookup
   - Check if `execution_context` is properly serialized/deserialized

4. **Test Workflow Orchestrator:**
   - Verify `workflow_orchestrator.execute_workflow()` completes successfully
   - Verify result structure matches expected format
   - Check if result is properly saved to `execution_context`

## Related Files

### Playbook Spec
- `mindscape-ai-cloud/capabilities/ig/playbooks/specs/ig_analyze_following.json`
  - `execution_profile.execution_mode: "workflow"`
  - `output_artifacts` defined for artifact creation

### Backend Code
- `mindscape-ai-local-core/backend/app/routes/core/playbook_execution.py`
  - `start_playbook_execution()` - Start endpoint
  - `get_playbook_result()` - Result endpoint (issue here)

- `mindscape-ai-local-core/backend/app/services/playbook_run_executor.py`
  - `execute_playbook_run()` - Main executor
  - `_execute_workflow_legacy()` - Workflow execution (task creation/update)

- `mindscape-ai-local-core/backend/app/services/playbook_runner.py`
  - `get_playbook_execution_result()` - Conversation mode result retrieval

- `mindscape-ai-local-core/backend/app/services/workflow_orchestrator.py`
  - `execute_workflow()` - Workflow execution logic

### Frontend Code
- `mindscape-ai-cloud/capabilities/ig/ui/IGFollowingAnalyzer.tsx`
  - Polls `/api/v1/playbooks/execute/{execution_id}/result`
  - Expects result with `summary`, `accounts`, `metadata`

## Debugging Commands

### Test Execution Start
```bash
curl -X POST "http://localhost:8200/api/v1/playbooks/execute/start?playbook_code=ig_analyze_following&profile_id=default-user&workspace_id={workspace_id}&auto_execute=true" \
  -H "Content-Type: application/json" \
  -d '{"inputs":{"target_username":"hannah.beezy","workspace_id":"{workspace_id}","visit_account_pages":false,"max_accounts":2}}'
```

### Check Execution Result
```bash
curl "http://localhost:8200/api/v1/playbooks/execute/{execution_id}/result"
```

### Check Task in Database
```bash
curl "http://localhost:8200/api/v1/workspaces/{workspace_id}/executions?playbook_code=ig_analyze_following&limit=5"
```

## Status

**Current Status:** 🔴 **BLOCKED**

**Last Updated:** 2026-01-18

**Blocking Issue:** Tool `ig.ig_analyze_following` not registered in MindscapeTool registry at application startup.

## Root Cause Analysis (2026-01-18)

### Finding 1: ToolSourceType.CAPABILITY_PACK Not Defined
- **File:** `mindscape-ai-local-core/backend/app/capabilities/tool_loader.py` line 85
- **Issue:** `ToolSourceType.CAPABILITY_PACK` does not exist in enum
- **Fix:** Changed to `ToolSourceType.BUILTIN`

### Finding 2: load_all_capability_tools() Not Called on Startup
- **File:** `mindscape-ai-local-core/backend/app/main.py`
- **Issue:** `load_capabilities()` only loads manifest info to registry dict, but doesn't register tools to MindscapeTool registry
- **Fix:** Added `load_all_capability_tools()` call after `load_capabilities()`

### Finding 3: tool_slot_resolver Uses Hardcoded known_capabilities
- **File:** `mindscape-ai-local-core/backend/app/services/tool_slot_resolver.py`
- **Issue:** `_looks_like_tool_id()` uses hardcoded list that doesn't include `ig`
- **Fix:** Changed to dynamically check `get_mindscape_tool(slot)` from registry

### Finding 4: Module Import Path Issue
- **Issue:** Manifest uses `capabilities.ig.tools.xxx` but container expects `app.capabilities.ig.tools.xxx`
- **Evidence:** Error log: `Failed to import module capabilities.ig.tools.ig_hashtag_manager_tool for tool ig.ig_hashtag_manager_tool: No module named 'capabilities'`
- **Note:** Some tools successfully load via fallback path handling in tool_loader

### Current Test Result (Manual)
```python
# After calling load_capabilities() and load_all_capability_tools() manually:
ig.ig_analyze_following registered: True
Tools loaded: 52
```

### Remaining Issue
- Tool loads successfully when tested manually
- But still fails when executed via API endpoint
- Possible cause: Registry state not persisted between application workers or startup sequence issue
