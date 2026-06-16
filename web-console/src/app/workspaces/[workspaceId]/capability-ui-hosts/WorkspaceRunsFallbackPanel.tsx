'use client';

import React, { useEffect, useMemo, useState } from 'react';

import { RunnerTaskCard } from '@/components/runner/RunnerTaskCard';
import { useWorkspaceDataOptional } from '@/contexts/WorkspaceDataContext';
import { isDocumentHidden } from '@/lib/page-visibility';
import { sharedGetFetch } from '@/lib/resilient-fetch';

type WorkspaceExecutionLike = Record<string, any>;

const WORKSPACE_RUNS_FALLBACK_POLL_MS = 20_000;
const WORKSPACE_RUNS_FALLBACK_TIMEOUT_MS = 12_000;

function isActiveExecutionStatus(status: unknown): boolean {
  const normalized = String(status || '').toLowerCase();
  return normalized === 'running' || normalized === 'queued' || normalized === 'pending' || normalized === 'paused';
}

function normalizeBaseUrl(apiUrl: string): string {
  return apiUrl.replace(/\/$/, '');
}

function executionId(execution: WorkspaceExecutionLike): string {
  return String(execution.execution_id || execution.id || execution.task_id || '');
}

function executionPlaybookCode(execution: WorkspaceExecutionLike): string {
  return String(execution.playbook_code || execution.pack_id || execution.task?.pack_id || execution.task_type || '');
}

function executionParams(execution: WorkspaceExecutionLike): Record<string, any> {
  const context = execution.execution_context || {};
  return {
    ...(context.inputs || {}),
    ...(execution.task?.params || {}),
    ...(execution.params || {}),
  };
}

function executionProgress(execution: WorkspaceExecutionLike) {
  const context = execution.execution_context || {};
  if (context.progress && typeof context.progress === 'object') return context.progress;
  if (
    typeof execution.current_step_index === 'number' ||
    typeof execution.total_steps === 'number'
  ) {
    return {
      current_step_index: execution.current_step_index,
      total_steps: execution.total_steps,
      current_step_name: execution.current_step_name,
    };
  }
  return null;
}

function firstString(...values: unknown[]): string | null {
  for (const value of values) {
    const normalized = String(value ?? '').trim();
    if (normalized) return normalized;
  }
  return null;
}

function mergeExecutions(
  primary: WorkspaceExecutionLike[],
  secondary: WorkspaceExecutionLike[],
): WorkspaceExecutionLike[] {
  const seen = new Set<string>();
  const merged: WorkspaceExecutionLike[] = [];
  for (const execution of [...primary, ...secondary]) {
    if (!isActiveExecutionStatus(execution.status)) continue;
    const id = executionId(execution);
    const key = id || JSON.stringify([
      executionPlaybookCode(execution),
      execution.status,
      execution.created_at,
      execution.started_at,
    ]);
    if (seen.has(key)) continue;
    seen.add(key);
    merged.push(execution);
  }
  return merged;
}

function buildExecutionsUrl(params: {
  apiUrl: string;
  workspaceId: string;
  statuses: string[];
  limit: number;
  activeOnly?: boolean;
  orderBy?: string;
  order?: 'asc' | 'desc';
}): string {
  const search = new URLSearchParams();
  search.set('limit', String(params.limit));
  if (params.activeOnly) search.set('active_only', 'true');
  if (params.orderBy) search.set('order_by', params.orderBy);
  if (params.order) search.set('order', params.order);
  for (const status of params.statuses) {
    search.append('status', status);
  }
  return `${normalizeBaseUrl(params.apiUrl)}/api/v1/workspaces/${encodeURIComponent(params.workspaceId)}/executions?${search.toString()}`;
}

async function fetchWorkspaceRunsFallbackExecutions(params: {
  apiUrl: string;
  workspaceId: string;
  signal: AbortSignal;
}): Promise<WorkspaceExecutionLike[]> {
  const activeUrl = buildExecutionsUrl({
    apiUrl: params.apiUrl,
    workspaceId: params.workspaceId,
    statuses: ['running', 'paused'],
    limit: 50,
    orderBy: 'started_at',
    order: 'desc',
  });
  const pendingUrl = buildExecutionsUrl({
    apiUrl: params.apiUrl,
    workspaceId: params.workspaceId,
    statuses: ['queued', 'pending'],
    limit: 30,
    activeOnly: true,
    orderBy: 'created_at',
    order: 'desc',
  });

  const [activeResponse, pendingResponse] = await Promise.all([
    sharedGetFetch(
      activeUrl,
      { method: 'GET', signal: params.signal },
      { dedupKey: `workspace-runs-fallback:active:${params.workspaceId}` },
    ),
    sharedGetFetch(
      pendingUrl,
      { method: 'GET', signal: params.signal },
      { dedupKey: `workspace-runs-fallback:pending:${params.workspaceId}` },
    ),
  ]);

  if (!activeResponse.ok) {
    throw new Error(`Failed to load active workspace executions: ${activeResponse.status}`);
  }
  if (!pendingResponse.ok) {
    throw new Error(`Failed to load pending workspace executions: ${pendingResponse.status}`);
  }

  const activeData = await activeResponse.json();
  const pendingData = await pendingResponse.json();
  return mergeExecutions(activeData.executions || [], pendingData.executions || []);
}

function useWorkspaceRunsFallbackExecutions(params: {
  apiUrl: string;
  workspaceId: string;
  enabled: boolean;
}) {
  const [executions, setExecutions] = useState<WorkspaceExecutionLike[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!params.enabled || !params.workspaceId) {
      setExecutions([]);
      setIsLoading(false);
      setError(null);
      return undefined;
    }

    let cancelled = false;
    let intervalId: ReturnType<typeof setInterval> | null = null;
    let activeController: AbortController | null = null;

    const load = async () => {
      if (isDocumentHidden()) return;
      activeController?.abort();
      const controller = new AbortController();
      activeController = controller;
      const timeoutId = setTimeout(() => controller.abort(), WORKSPACE_RUNS_FALLBACK_TIMEOUT_MS);
      setIsLoading(true);
      try {
        const nextExecutions = await fetchWorkspaceRunsFallbackExecutions({
          apiUrl: params.apiUrl,
          workspaceId: params.workspaceId,
          signal: controller.signal,
        });
        if (!cancelled) {
          setExecutions(nextExecutions);
          setError(null);
        }
      } catch (err) {
        if (!cancelled && !(err instanceof DOMException && err.name === 'AbortError')) {
          setError(err instanceof Error ? err.message : 'Failed to load workspace runs');
        }
      } finally {
        clearTimeout(timeoutId);
        if (!cancelled) {
          setIsLoading(false);
        }
      }
    };

    void load();
    intervalId = setInterval(load, WORKSPACE_RUNS_FALLBACK_POLL_MS);

    return () => {
      cancelled = true;
      activeController?.abort();
      if (intervalId) clearInterval(intervalId);
    };
  }, [params.apiUrl, params.enabled, params.workspaceId]);

  return { executions, isLoading, error };
}

function WorkspaceExecutionFields({ execution }: { execution: WorkspaceExecutionLike }) {
  const params = executionParams(execution);
  const context = execution.execution_context || {};
  const source = firstString(params.source_handle, params.source_username, context.source_handle);
  const target = firstString(params.target_handle, params.target_username, context.target_handle, context.target_username);
  const reference = firstString(params.reference_id, params.ref_id, context.reference_id, context.ref_id);
  const trigger = firstString(params.trigger, context.trigger);
  const queueShard = firstString(execution.queue_shard);
  const blockedReason = firstString(execution.blocked_reason);

  return (
    <div className="space-y-1 text-[10px] leading-snug text-gray-500 dark:text-gray-400">
      <div className="grid grid-cols-[4.5rem,minmax(0,1fr)] gap-x-2 gap-y-1">
        {source ? (
          <>
            <span className="font-semibold uppercase text-gray-400 dark:text-gray-500">Source</span>
            <span className="min-w-0 truncate">{source}</span>
          </>
        ) : null}
        {target ? (
          <>
            <span className="font-semibold uppercase text-gray-400 dark:text-gray-500">Target</span>
            <span className="min-w-0 truncate">{target}</span>
          </>
        ) : null}
        {reference ? (
          <>
            <span className="font-semibold uppercase text-gray-400 dark:text-gray-500">Reference</span>
            <span className="min-w-0 truncate font-mono">{reference}</span>
          </>
        ) : null}
        {trigger ? (
          <>
            <span className="font-semibold uppercase text-gray-400 dark:text-gray-500">Trigger</span>
            <span className="min-w-0 truncate">{trigger}</span>
          </>
        ) : null}
        {queueShard ? (
          <>
            <span className="font-semibold uppercase text-gray-400 dark:text-gray-500">Queue</span>
            <span className="min-w-0 truncate">{queueShard}</span>
          </>
        ) : null}
        {blockedReason ? (
          <>
            <span className="font-semibold uppercase text-gray-400 dark:text-gray-500">Blocked</span>
            <span className="min-w-0 truncate">{blockedReason}</span>
          </>
        ) : null}
      </div>
    </div>
  );
}

export default function WorkspaceRunsFallbackPanel({
  apiUrl,
  workspaceId,
}: {
  apiUrl: string;
  workspaceId: string;
}) {
  const workspaceData = useWorkspaceDataOptional();
  const fallbackState = useWorkspaceRunsFallbackExecutions({
    apiUrl,
    workspaceId,
    enabled: true,
  });
  const contextActiveExecutions = useMemo(
    () => (workspaceData?.executions || []).filter((execution) => isActiveExecutionStatus(execution.status)),
    [workspaceData?.executions],
  );
  const activeExecutions = useMemo(
    () => mergeExecutions(fallbackState.executions, contextActiveExecutions),
    [contextActiveExecutions, fallbackState.executions],
  );
  const runningCount = activeExecutions.filter((execution) => String(execution.status).toLowerCase() === 'running').length;
  const pendingCount = activeExecutions.filter((execution) => String(execution.status).toLowerCase() === 'pending' || String(execution.status).toLowerCase() === 'queued').length;

  return (
    <div className="space-y-3 bg-white p-3 dark:bg-gray-950">
      <div className="mb-3 flex items-center justify-between gap-2">
        <div className="text-xs font-semibold uppercase tracking-normal text-gray-500 dark:text-gray-400">
          Workspace runs
        </div>
        <div className="shrink-0 rounded border border-gray-200 bg-gray-50 px-2 py-1 text-[10px] font-semibold text-gray-500 dark:border-gray-800 dark:bg-gray-900 dark:text-gray-400">
          {runningCount} running · {pendingCount} pending
        </div>
      </div>
      {fallbackState.error && activeExecutions.length === 0 ? (
        <div className="rounded border border-red-200 bg-red-50 p-2 text-xs text-red-700 dark:border-red-800/50 dark:bg-red-900/10 dark:text-red-300">
          {fallbackState.error}
        </div>
      ) : null}
      {fallbackState.isLoading && activeExecutions.length === 0 ? (
        <div className="text-xs text-gray-500 dark:text-gray-400">Loading workspace runs...</div>
      ) : null}
      {activeExecutions.length > 0 ? (
        <div className="space-y-2">
          {activeExecutions.map((execution) => {
            const id = executionId(execution);
            const playbookCode = executionPlaybookCode(execution);
            return (
              <RunnerTaskCard
                key={id || `${playbookCode}:${execution.created_at}`}
                status={execution.status}
                playbookCode={playbookCode}
                title={playbookCode || id}
                heartbeatAt={execution.heartbeat_at || execution.execution_context?.heartbeat_at}
                runnerId={execution.runner_id || execution.execution_context?.runner_id}
                progress={executionProgress(execution)}
                executionId={id}
                queuePosition={execution.queue_position}
                queueTotal={execution.queue_total}
                error={execution.error}
                createdAt={execution.created_at || execution.started_at}
                extensionSlot={<WorkspaceExecutionFields execution={execution} />}
              />
            );
          })}
        </div>
      ) : !fallbackState.isLoading ? (
        <div className="rounded border border-gray-200 bg-gray-50 p-3 text-xs text-gray-500 dark:border-gray-800 dark:bg-gray-900 dark:text-gray-400">
          No active runs.
        </div>
      ) : null}
    </div>
  );
}
