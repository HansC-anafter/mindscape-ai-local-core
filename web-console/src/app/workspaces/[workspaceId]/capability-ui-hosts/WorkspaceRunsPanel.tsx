'use client';

import React, { useEffect, useState } from 'react';

import { Activity, PauseCircle } from 'lucide-react';

import WorkspacePausedRunsPanel from '@/components/workspace/WorkspacePausedRunsPanel';
import WorkspaceRunObservationsPanel from '@/components/workspace/WorkspaceRunObservationsPanel';
import { useWorkspaceDataOptional } from '@/contexts/WorkspaceDataContext';
import { getApiBaseUrl } from '@/lib/api-url';
import {
  type WorkspaceToolDefinition,
} from '@/lib/workspace-tools/workspace-tool-registry';
import type { UseRunObservationsSummaryResult } from '@/lib/workspace-runs/useRunObservationsSummary';
import { getWorkspaceToolDefinitions } from './useWorkspaceToolDefinitions';

interface WorkspaceRunsPanelProps {
  workspaceId: string;
  activeCapabilityCode: string;
  runObservationsSummary?: UseRunObservationsSummaryResult;
}

type WorkspaceRunsView = 'active' | 'paused';

function isActiveExecutionStatus(status: unknown): boolean {
  const normalized = String(status || '').toLowerCase();
  return normalized === 'running' || normalized === 'queued' || normalized === 'pending' || normalized === 'paused';
}

function WorkspaceRunsFallbackPanel() {
  const workspaceData = useWorkspaceDataOptional();
  const executions = workspaceData?.executions || [];
  const activeExecutions = executions.filter((execution) => isActiveExecutionStatus(execution.status));

  return (
    <div className="space-y-3 bg-white p-3 dark:bg-gray-950">
      <div className="mb-3 text-xs font-semibold uppercase tracking-normal text-gray-500 dark:text-gray-400">
        Workspace runs
      </div>
      {activeExecutions.length > 0 ? (
        <div className="space-y-2">
          {activeExecutions.map((execution) => (
            <div
              key={execution.id}
              className="rounded border border-gray-200 bg-gray-50 p-3 text-xs dark:border-gray-800 dark:bg-gray-900"
            >
              <div className="font-medium text-gray-900 dark:text-gray-100">
                {execution.playbook_code || execution.id}
              </div>
              <div className="mt-1 text-gray-500 dark:text-gray-400">
                {execution.status}
              </div>
            </div>
          ))}
        </div>
      ) : (
        <div className="rounded border border-gray-200 bg-gray-50 p-3 text-xs text-gray-500 dark:border-gray-800 dark:bg-gray-900 dark:text-gray-400">
          No active runs.
        </div>
      )}
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
    <>
      <WorkspaceRunObservationsPanel workspaceId={workspaceId} apiUrl={apiUrl} summaryState={runObservationsSummary} compact showEmptyState={false} />
      <div className="p-2 text-xs text-gray-500 dark:text-gray-400">
        Loading capability runs...
      </div>
    </>
  ) : !Component ? (
    <>
      <WorkspaceRunObservationsPanel workspaceId={workspaceId} apiUrl={apiUrl} summaryState={runObservationsSummary} compact showEmptyState={false} />
      <WorkspaceRunsFallbackPanel />
    </>
  ) : (
    <>
      <WorkspaceRunObservationsPanel workspaceId={workspaceId} apiUrl={apiUrl} summaryState={runObservationsSummary} compact showEmptyState={false} />
      <div className="min-h-0 flex-1 overflow-hidden">
        <Component workspaceId={workspaceId} apiUrl={apiUrl} embedded />
      </div>
    </>
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
