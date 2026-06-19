'use client';

import React, { useCallback, useEffect, useState } from 'react';
import { RefreshCw } from 'lucide-react';

import { useWorkspaceDataOptional } from '@/contexts/WorkspaceDataContext';
import { isDocumentHidden } from '@/lib/page-visibility';
import { openAppRouteInNewWindow } from '@/lib/navigation/openAppRouteInNewWindow';
import {
  WorkspaceAgentsStatusCard,
  type WorkspaceAgentsStatusSnapshot,
} from '@/components/workspace/WorkspaceAgentsStatusCard';
import {
  HostResourceStatusSummaryCard,
  type HostResourceSummary,
} from './HostResourceStatusSummaryCard';

interface StatusSnapshot {
  agents: WorkspaceAgentsStatusSnapshot | null;
  xtts: Record<string, any> | null;
  mcpGateway: Record<string, any> | null;
  hostResources: HostResourceSummary | null;
  updatedAt: string;
}

export function StatusSection({
  apiUrl,
  workspaceId,
}: {
  apiUrl: string;
  workspaceId: string;
}) {
  const workspaceData = useWorkspaceDataOptional();
  const [loading, setLoading] = useState(false);
  const [statusError, setStatusError] = useState<string | null>(null);
  const [snapshot, setSnapshot] = useState<StatusSnapshot | null>(null);
  const refreshAllWorkspace = workspaceData?.refreshAll;
  const refreshSystemStatus = workspaceData?.refreshSystemStatus;

  const loadSnapshot = useCallback(async (shouldRefreshAll: boolean) => {
    if (isDocumentHidden()) {
      return;
    }
    setLoading(true);
    setStatusError(null);
    try {
      let workspaceStatusRefresh = Promise.resolve();
      if (shouldRefreshAll) {
        workspaceStatusRefresh = refreshAllWorkspace
          ? refreshAllWorkspace()
          : (refreshSystemStatus ? refreshSystemStatus({ force: true }) : Promise.resolve());
      }
      const [agents, xtts, mcpGateway, hostResources] = await Promise.allSettled([
        fetch(`${apiUrl}/api/v1/workspaces/${workspaceId}/agents`),
        fetch(`${apiUrl}/api/v1/host/services/xtts/health`),
        fetch(`${apiUrl}/api/v1/host/services/mcp-gateway/health`),
        fetch(`${apiUrl}/api/v1/host-resources/summary${shouldRefreshAll ? '?refresh=true' : '?allow_stale=true'}`),
        workspaceStatusRefresh,
      ]);
      setSnapshot({
        agents: agents.status === 'fulfilled' && agents.value.ok ? await agents.value.json().catch(() => null) : null,
        xtts: xtts.status === 'fulfilled' && xtts.value.ok ? await xtts.value.json().catch(() => null) : null,
        mcpGateway: mcpGateway.status === 'fulfilled' && mcpGateway.value.ok ? await mcpGateway.value.json().catch(() => null) : null,
        hostResources: hostResources.status === 'fulfilled' && hostResources.value.ok
          ? await hostResources.value.json().catch(() => null)
          : null,
        updatedAt: new Date().toLocaleTimeString(),
      });
    } catch (error) {
      setStatusError(error instanceof Error ? error.message : 'Status refresh failed');
    } finally {
      setLoading(false);
    }
  }, [apiUrl, refreshAllWorkspace, refreshSystemStatus, workspaceId]);

  useEffect(() => {
    void loadSnapshot(false);
  }, [loadSnapshot]);

  const systemStatus = workspaceData?.systemStatus;
  return (
    <div className="space-y-3" data-testid="workspace-settings-status-section">
      <div className="flex items-center justify-between gap-2">
        <div className="min-w-0">
          <div className="text-xs font-semibold uppercase text-gray-500 dark:text-gray-400">System</div>
          <div className="truncate text-sm font-semibold">{systemStatus?.llm_provider || 'Runtime snapshot'}</div>
        </div>
        <button
          type="button"
          className="inline-flex h-8 w-8 items-center justify-center rounded border border-gray-200 text-gray-600 hover:bg-gray-50 dark:border-gray-700 dark:text-gray-300 dark:hover:bg-gray-900"
          aria-label="Refresh status"
          onClick={() => void loadSnapshot(true)}
        >
          <RefreshCw aria-hidden="true" className={`h-4 w-4 ${loading ? 'animate-spin' : ''}`} />
        </button>
      </div>
      <div className="grid grid-cols-2 gap-2">
        <StatusMetric label="LLM" value={systemStatus?.llm_configured ? 'Ready' : 'Unset'} />
        <StatusMetric label="Vector DB" value={systemStatus?.vector_db_connected ? 'Ready' : 'Offline'} />
        <StatusMetric label="Issues" value={String(systemStatus?.critical_issues_count ?? 0)} />
        <StatusMetric label="Updated" value={snapshot?.updatedAt || '-'} />
      </div>
      <WorkspaceAgentsStatusCard
        workspaceId={workspaceId}
        apiUrl={apiUrl}
        agentsSnapshot={snapshot?.agents || null}
        onBridgeServiceChanged={() => void loadSnapshot(false)}
      />
      <div className="rounded border border-gray-200 p-2 text-xs dark:border-gray-800">
        <div className="flex justify-between gap-2 py-1">
          <span className="text-gray-500 dark:text-gray-400">XTTS</span>
          <span className="truncate font-medium">{snapshot?.xtts?.status || snapshot?.xtts?.state || 'Unchecked'}</span>
        </div>
        <div className="flex justify-between gap-2 py-1">
          <span className="text-gray-500 dark:text-gray-400">MCP Gateway</span>
          <span className="truncate font-medium">{snapshot?.mcpGateway?.status || snapshot?.mcpGateway?.state || 'Unchecked'}</span>
        </div>
      </div>
      <HostResourceStatusSummaryCard
        summary={snapshot?.hostResources || null}
        loading={loading}
        onOpenDashboard={() => openAppRouteInNewWindow(`/settings?tab=runtime&section=host-resources&workspace_id=${encodeURIComponent(workspaceId)}`)}
      />
      {statusError ? (
        <div className="rounded border border-red-200 bg-red-50 p-2 text-xs text-red-700 dark:border-red-900 dark:bg-red-950/30 dark:text-red-300">
          {statusError}
        </div>
      ) : null}
    </div>
  );
}

function StatusMetric({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded border border-gray-200 p-2 dark:border-gray-800">
      <div className="text-[10px] font-semibold uppercase text-gray-500 dark:text-gray-400">{label}</div>
      <div className="truncate text-sm font-semibold">{value}</div>
    </div>
  );
}
