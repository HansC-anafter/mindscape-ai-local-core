'use client';

import React, { useMemo, useState } from 'react';
import { Bot, WifiOff } from 'lucide-react';

import { WorkspaceBridgeGuideFloatingPanel } from './WorkspaceBridgeGuideFloatingPanel';

export interface WorkspaceStatusAgentInfo {
  id: string;
  name?: string | null;
  status?: string | null;
  transport?: string | null;
  reason?: string | null;
}

export interface WorkspaceAgentsStatusSnapshot {
  agents?: WorkspaceStatusAgentInfo[];
  bridge_script_path?: string | null;
}

interface WorkspaceAgentsStatusCardProps {
  workspaceId: string;
  apiUrl: string;
  agentsSnapshot: WorkspaceAgentsStatusSnapshot | null;
  onBridgeServiceChanged?: () => void;
}

function getAgentLabel(agent: WorkspaceStatusAgentInfo): string {
  if (agent.status === 'available' && agent.transport === 'ws') {
    return 'Connected (WS)';
  }
  if (agent.status === 'available') {
    return 'Connected';
  }
  if (agent.reason === 'no_ws_client') {
    return 'Start Bridge';
  }
  return agent.reason || agent.status || 'Unavailable';
}

function getAgentDotClass(agent: WorkspaceStatusAgentInfo): string {
  if (agent.status === 'available') {
    return 'bg-emerald-500';
  }
  if (agent.reason === 'no_ws_client') {
    return 'bg-amber-500';
  }
  return 'bg-gray-300 dark:bg-gray-700';
}

export function WorkspaceAgentsStatusCard({
  workspaceId,
  apiUrl,
  agentsSnapshot,
  onBridgeServiceChanged,
}: WorkspaceAgentsStatusCardProps) {
  const [bridgeGuideOpen, setBridgeGuideOpen] = useState(false);
  const agents = useMemo(() => agentsSnapshot?.agents || [], [agentsSnapshot?.agents]);
  const connectedAgents = agents.filter((agent) => agent.status === 'available').length;
  const summary = agentsSnapshot
    ? (agents.length > 0 ? `${connectedAgents}/${agents.length} connected` : 'No agents')
    : 'Unchecked';

  return (
    <div className="rounded border border-gray-200 p-2 text-xs dark:border-gray-800" data-testid="workspace-agents-status-card">
      <div className="flex items-start justify-between gap-3 py-1">
        <div className="flex min-w-0 items-start gap-2">
          <Bot aria-hidden="true" className="mt-0.5 h-4 w-4 shrink-0 text-gray-500" />
          <div className="min-w-0">
            <div className="font-semibold text-gray-900 dark:text-gray-100">CLI Agents</div>
            <div className="text-gray-500 dark:text-gray-400">{summary}</div>
          </div>
        </div>
        <button
          type="button"
          aria-label="How to connect CLI bridge"
          className="inline-flex shrink-0 items-center gap-1 rounded border border-gray-200 px-2 py-1 font-semibold text-gray-700 hover:bg-gray-50 dark:border-gray-700 dark:text-gray-200 dark:hover:bg-gray-900"
          onClick={() => setBridgeGuideOpen(true)}
        >
          <WifiOff aria-hidden="true" className="h-3.5 w-3.5" />
          Connect bridge
        </button>
      </div>
      {agents.length > 0 ? (
        <div className="mt-2 space-y-1">
          {agents.map((agent) => (
            <div key={agent.id} className="flex items-start justify-between gap-2 rounded bg-gray-50 px-2 py-1.5 dark:bg-gray-900">
              <div className="flex min-w-0 items-center gap-2">
                <span aria-hidden="true" className={`h-2 w-2 shrink-0 rounded-full ${getAgentDotClass(agent)}`} />
                <span className="min-w-0 break-words font-medium text-gray-800 dark:text-gray-100">
                  {agent.name || agent.id}
                </span>
              </div>
              <span className="shrink-0 text-right text-gray-500 dark:text-gray-400">{getAgentLabel(agent)}</span>
            </div>
          ))}
        </div>
      ) : null}
      <WorkspaceBridgeGuideFloatingPanel
        open={bridgeGuideOpen}
        workspaceId={workspaceId}
        apiUrl={apiUrl}
        bridgeScriptPath={agentsSnapshot?.bridge_script_path || null}
        onBridgeServiceChanged={onBridgeServiceChanged}
        onClose={() => setBridgeGuideOpen(false)}
      />
    </div>
  );
}
