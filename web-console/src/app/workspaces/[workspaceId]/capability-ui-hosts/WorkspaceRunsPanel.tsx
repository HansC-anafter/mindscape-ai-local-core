'use client';

import React, { useEffect, useState } from 'react';

import { useWorkspaceDataOptional } from '@/contexts/WorkspaceDataContext';
import { getApiBaseUrl } from '@/lib/api-url';
import {
  loadCapabilityUIComponent,
  primeCapabilityUIComponentMetadata,
} from '@/lib/capability-ui-loader';
import {
  fetchWorkspaceToolDefinitions,
  type WorkspaceToolDefinition,
} from '@/lib/workspace-tools/workspace-tool-registry';

interface WorkspaceRunsPanelProps {
  workspaceId: string;
  activeCapabilityCode: string;
}

function isActiveExecutionStatus(status: unknown): boolean {
  const normalized = String(status || '').toLowerCase();
  return normalized === 'running' || normalized === 'queued' || normalized === 'pending' || normalized === 'paused';
}

function WorkspaceRunsFallbackPanel() {
  const workspaceData = useWorkspaceDataOptional();
  const executions = workspaceData?.executions || [];
  const activeExecutions = executions.filter((execution) => isActiveExecutionStatus(execution.status));

  return (
    <div className="h-full overflow-y-auto bg-white p-4 dark:bg-gray-950">
      <div className="mb-3 text-xs font-semibold uppercase tracking-normal text-gray-500 dark:text-gray-400">
        Runs
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

export default function WorkspaceRunsPanel({
  workspaceId,
  activeCapabilityCode,
}: WorkspaceRunsPanelProps) {
  const apiUrl = getApiBaseUrl();
  const [Component, setComponent] = useState<React.ComponentType<any> | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setComponent(null);
    void fetchWorkspaceToolDefinitions({ apiUrl, capabilityCode: activeCapabilityCode })
      .then(async (tools) => {
        const runsPanelTool = tools.find(isRunsPanelTool);
        if (!runsPanelTool) {
          return null;
        }
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

  if (loading) {
    return (
      <div className="flex h-full items-center justify-center text-xs text-gray-500 dark:text-gray-400">
        Loading runs...
      </div>
    );
  }

  if (!Component) {
    return <WorkspaceRunsFallbackPanel />;
  }

  return <Component workspaceId={workspaceId} apiUrl={apiUrl} />;
}
