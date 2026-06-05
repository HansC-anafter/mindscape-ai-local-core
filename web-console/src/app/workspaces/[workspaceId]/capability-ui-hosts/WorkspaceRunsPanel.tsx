'use client';

import React, { useEffect, useMemo, useState } from 'react';

import { Activity, PauseCircle } from 'lucide-react';

import { RunnerTaskCard } from '@/components/runner/RunnerTaskCard';
import WorkspacePausedRunsPanel from '@/components/workspace/WorkspacePausedRunsPanel';
import WorkspaceRunObservationsPanel from '@/components/workspace/WorkspaceRunObservationsPanel';
import { useWorkspaceDataOptional } from '@/contexts/WorkspaceDataContext';
import { getApiBaseUrl } from '@/lib/api-url';
import { isDocumentHidden } from '@/lib/page-visibility';
import { sharedGetFetch } from '@/lib/resilient-fetch';
import {
  type WorkspaceToolDefinition,
} from '@/lib/workspace-tools/workspace-tool-registry';
import type { UseRunObservationsSummaryResult } from '@/lib/workspace-runs/useRunObservationsSummary';
import { getWorkspaceToolDefinitions } from './useWorkspaceToolDefinitions';

interface WorkspaceRunsPanelProps {
  workspaceId: string;
  activeCapabilityCode: string | null;
  runObservationsSummary?: UseRunObservationsSummaryResult;
}

type WorkspaceRunsView = 'active' | 'paused';
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

function WorkspaceRunsFallbackPanel({
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

function isRunsPanelTool(tool: WorkspaceToolDefinition): boolean {
  return tool.id === 'runs_panel' && tool.group === 'capability';
}

function WorkspaceRunsViewTabs({
  activeView,
  setActiveView,
}: {
  activeView: WorkspaceRunsView;
  setActiveView: (view: WorkspaceRunsView) => void;
}) {
  const tabs = [
    { id: 'active' as const, label: 'Active Runs', icon: Activity },
    { id: 'paused' as const, label: 'Paused Runs', icon: PauseCircle },
  ];
  return (
    <div className="flex shrink-0 items-center gap-1 border-b border-gray-200 px-2 py-2 dark:border-gray-800">
      {tabs.map((tab) => {
        const Icon = tab.icon;
        const active = activeView === tab.id;
        return (
          <button
            key={tab.id}
            type="button"
            data-testid={`workspace-runs-view-${tab.id}`}
            onClick={() => setActiveView(tab.id)}
            className={`h-8 rounded-md border px-2 text-xs font-semibold uppercase tracking-normal flex items-center gap-2 ${
              active
                ? 'border-gray-300 bg-gray-100 text-gray-900 dark:border-gray-600 dark:bg-gray-800 dark:text-gray-100'
                : 'border-transparent bg-transparent text-gray-600 hover:bg-gray-50 dark:text-gray-300 dark:hover:bg-gray-800/70'
            }`}
            aria-label={tab.label}
            title={tab.label}
          >
            <Icon className="h-3.5 w-3.5" />
            <span>{tab.label.replace(' Runs', '')}</span>
          </button>
        );
      })}
    </div>
  );
}

export default function WorkspaceRunsPanel({
  workspaceId,
  activeCapabilityCode,
  runObservationsSummary,
}: WorkspaceRunsPanelProps) {
  const apiUrl = getApiBaseUrl();
  const workspaceData = useWorkspaceDataOptional();
  const [activeView, setActiveView] = useState<WorkspaceRunsView>('active');
  const [Component, setComponent] = useState<React.ComponentType<any> | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    void workspaceData?.refreshExecutions?.();
  }, [workspaceData?.refreshExecutions]);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setComponent(null);
    if (!activeCapabilityCode) {
      setLoading(false);
      return () => {
        cancelled = true;
      };
    }
    void getWorkspaceToolDefinitions(apiUrl, activeCapabilityCode)
      .then(async (tools) => {
        const runsPanelTool = tools.find(isRunsPanelTool);
        if (!runsPanelTool) {
          return null;
        }
        const {
          loadCapabilityUIComponent,
          primeCapabilityUIComponentMetadata,
        } = await import('@/lib/capability-ui-loader');
        primeCapabilityUIComponentMetadata(
          runsPanelTool.capability_code,
          [runsPanelTool.panel_component],
        );
        return loadCapabilityUIComponent(
          runsPanelTool.capability_code,
          runsPanelTool.panel_component_code,
          apiUrl,
        );
      })
      .then((LoadedComponent) => {
        if (!cancelled) {
          setComponent(() => LoadedComponent);
          setLoading(false);
        }
      })
      .catch(() => {
        if (!cancelled) {
          setComponent(null);
          setLoading(false);
        }
      });
    return () => {
      cancelled = true;
    };
  }, [activeCapabilityCode, apiUrl]);

  const activeContent = loading ? (
    <div className="p-2 text-xs text-gray-500 dark:text-gray-400">
      Loading capability runs...
    </div>
  ) : !Component ? (
    <>
      <WorkspaceRunObservationsPanel workspaceId={workspaceId} apiUrl={apiUrl} summaryState={runObservationsSummary} compact showEmptyState={false} />
      <WorkspaceRunsFallbackPanel workspaceId={workspaceId} apiUrl={apiUrl} />
    </>
  ) : (
    <div className="min-h-0 flex-1 overflow-hidden">
      <Component workspaceId={workspaceId} apiUrl={apiUrl} embedded />
    </div>
  );

  if (activeView === 'paused') {
    return (
      <div className="flex h-full min-h-0 flex-col">
        <WorkspaceRunsViewTabs activeView={activeView} setActiveView={setActiveView} />
        <div className="min-h-0 flex-1 overflow-y-auto p-2">
          <WorkspacePausedRunsPanel workspaceId={workspaceId} apiUrl={apiUrl} summaryState={runObservationsSummary} />
        </div>
      </div>
    );
  }

  return (
    <div className="flex h-full min-h-0 flex-col">
      <WorkspaceRunsViewTabs activeView={activeView} setActiveView={setActiveView} />
      <div className="flex min-h-0 flex-1 flex-col overflow-hidden">
        {activeContent}
      </div>
    </div>
  );
}
