import { useEffect, useMemo, useRef, useState } from 'react';
import { MindscapeAPIClient } from '@/api/client';

type ExecutionStatus = 'queued' | 'running' | 'paused' | 'completed' | 'failed' | string;

export interface AccountsRunStatus {
  execution_id: string;
  playbook_code: string;
  status: ExecutionStatus;
  execution_backend_hint?: string | null;
  created_at?: string;
  started_at?: string;
  task_error?: string | null;
  failure_reason?: string | null;
  progress?: {
    stage?: string;
    total_accounts?: number;
    iteration?: number;
    reached_bottom?: boolean;
    no_change_count?: number;
    error_type?: string;
    error_message?: string;
    page_index?: number;
    page_total?: number;
    current_account?: string | null;
    updated_at?: string;
  } | null;
}

function areRunStatusEqual(
  a: AccountsRunStatus | null,
  b: AccountsRunStatus | null
): boolean {
  if (!a && !b) return true;
  if (!a || !b) return false;
  return (
    a.execution_id === b.execution_id &&
    a.playbook_code === b.playbook_code &&
    a.status === b.status &&
    (a.execution_backend_hint ?? null) === (b.execution_backend_hint ?? null) &&
    (a.created_at ?? null) === (b.created_at ?? null) &&
    (a.started_at ?? null) === (b.started_at ?? null) &&
    (a.task_error ?? null) === (b.task_error ?? null) &&
    (a.failure_reason ?? null) === (b.failure_reason ?? null)
  );
}

const toTime = (value: any): number => {
  const t = new Date(value || 0).getTime();
  return Number.isFinite(t) ? t : 0;
};

async function fetchWorkspaceExecutions(
  client: MindscapeAPIClient,
  workspaceId: string
): Promise<{ ok: boolean; executions: any[] }> {
  try {
    const resp = await client.get(`/api/v1/ig/workbench/sidebar-summary?workspace_id=${workspaceId}&active_limit=100`);
    if (!resp.ok) return { ok: false, executions: [] };
    const data = await resp.json().catch(() => ({}));
    return {
      ok: true,
      executions: Array.isArray(data.active_executions) ? data.active_executions : [],
    };
  } catch {
    return { ok: false, executions: [] };
  }
}

export function useAccountsRunStatus(params: {
  apiUrl: string;
  workspaceId: string;
}) {
  const { apiUrl, workspaceId } = params;
  const client = useMemo(() => MindscapeAPIClient.fromBaseUrl(apiUrl), [apiUrl]);
  const [runStatus, setRunStatus] = useState<AccountsRunStatus | null>(null);
  const dismissedExecutionIdRef = useRef<string | null>(null);

  const dismiss = (executionId: string) => {
    dismissedExecutionIdRef.current = executionId;
    setRunStatus((prev) => (prev?.execution_id === executionId ? null : prev));
  };

  const visibleRunStatus = useMemo(() => {
    if (!runStatus) return null;
    if (dismissedExecutionIdRef.current && dismissedExecutionIdRef.current === runStatus.execution_id) {
      return null;
    }
    return runStatus;
  }, [runStatus]);

  // Bootstrap only: discover whether the page loaded while an IG execution
  // was already active. Detailed progress lives on selected execution polling.
  useEffect(() => {
    let cancelled = false;

    const fetchOnce = async () => {
      try {
        const { ok, executions } = await fetchWorkspaceExecutions(client, workspaceId);
        if (cancelled || !ok) return;

        const running = executions.filter((e) => {
          const status = (e?.status || '').toString().toLowerCase();
          const code = (e?.playbook_code || '').toString();
          if (!code) return false;
          return (
            (status === 'running' || status === 'queued' || status === 'paused') &&
            (code === 'ig_analyze_following' || code === 'ig_capture_account_snapshot')
          );
        });

        if (running.length === 0) {
          if (!cancelled) {
            setRunStatus((prev) => (prev ? null : prev));
          }
          return;
        }

        const latest = [...running].sort(
          (a, b) => toTime(b.started_at || b.created_at) - toTime(a.started_at || a.created_at)
        )[0];

        const next: AccountsRunStatus = {
          execution_id: latest.execution_id,
          playbook_code: latest.playbook_code,
          status: latest.status,
          execution_backend_hint: null,
          created_at: latest.created_at,
          started_at: latest.started_at,
          task_error: latest?.task?.error || null,
          failure_reason: latest?.failure_reason || null,
          progress: null,
        };

        if (!cancelled) {
          setRunStatus((prev) => (areRunStatusEqual(prev, next) ? prev : next));
        }
      } catch {
        // Backend may be restarting — swallow silently
      }
    };

    void fetchOnce();
    return () => {
      cancelled = true;
    };
  }, [client, workspaceId]);

  return { runStatus: visibleRunStatus, dismiss };
}
