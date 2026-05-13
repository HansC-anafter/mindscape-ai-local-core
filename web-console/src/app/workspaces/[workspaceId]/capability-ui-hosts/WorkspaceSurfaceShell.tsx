'use client';

import React from 'react';
import { Activity, PanelRight, X } from 'lucide-react';

import { AOLRuntimeShellProvider } from '@/components/capabilities/aol-runtime-shell/AOLRuntimeShell';
import {
  WorkspaceToolRailButton,
  type WorkspaceToolRailGroup,
} from '@/components/workspace/WorkspaceToolRail';
import { useWorkspaceDataOptional } from '@/contexts/WorkspaceDataContext';
import type { WorkspaceToolDefinition } from '@/lib/workspace-tools/workspace-tool-registry';
import WorkspaceRuntimeFrame from '../components/WorkspaceRuntimeFrame';
import WorkspaceRunsPanel from './WorkspaceRunsPanel';
import WorkspaceToolExtensionSlot from './WorkspaceToolExtensionSlot';

interface WorkspaceSurfaceShellProps {
  workspaceId: string;
  activeCapabilityCode: string;
  surfacePath?: readonly string[];
  children: React.ReactNode;
}

const RESERVED_BUILT_IN_WORKSPACE_TOOL_IDS = new Set(['runs_panel']);

export default function WorkspaceSurfaceShell({
  workspaceId,
  activeCapabilityCode,
  surfacePath = [],
  children,
}: WorkspaceSurfaceShellProps) {
  return (
    <WorkspaceRuntimeFrame workspaceId={workspaceId}>
      <WorkspaceSurfaceShellContent
        workspaceId={workspaceId}
        activeCapabilityCode={activeCapabilityCode}
        surfacePath={surfacePath}
      >
        {children}
      </WorkspaceSurfaceShellContent>
    </WorkspaceRuntimeFrame>
  );
}

function WorkspaceSurfaceShellContent({
  workspaceId,
  activeCapabilityCode,
  surfacePath = [],
  children,
}: WorkspaceSurfaceShellProps) {
  const [activePanel, setActivePanel] = React.useState<string | null>(null);
  const [extensionTools, setExtensionTools] = React.useState<WorkspaceToolDefinition[]>([]);
  const workspaceData = useWorkspaceDataOptional();
  const activeExecutionCount = (workspaceData?.executions || []).filter((execution) => {
    const status = String(execution.status || '').toLowerCase();
    return status === 'running' || status === 'queued' || status === 'pending' || status === 'paused';
  }).length;
  const handleExtensionToolsChange = React.useCallback((tools: WorkspaceToolDefinition[]) => {
    setExtensionTools(
      tools.filter((tool) => !RESERVED_BUILT_IN_WORKSPACE_TOOL_IDS.has(tool.id)),
    );
  }, []);
  const toolGroups = React.useMemo<WorkspaceToolRailGroup[]>(() => {
    const groups: WorkspaceToolRailGroup[] = [{
      id: 'runs',
      label: 'Runs',
      testId: 'workspace-runs-tool-group',
      children: (
        <WorkspaceToolRailButton
          label="Runs"
          icon={<Activity aria-hidden="true" className="h-4 w-4" />}
          active={activePanel === 'runs'}
          badge={activeExecutionCount || null}
          testId="workspace-runs-tool"
          onClick={() => setActivePanel((current) => (current === 'runs' ? null : 'runs'))}
        />
      ),
    }];
    if (extensionTools.length > 0) {
      groups.push({
        id: 'capability-tools',
        label: 'Tools',
        testId: 'workspace-capability-tools-group',
        children: (
          <>
            {extensionTools.map((tool) => (
              <WorkspaceToolRailButton
                key={tool.tool_key}
                label={tool.label}
                icon={<PanelRight aria-hidden="true" className="h-4 w-4" />}
                active={activePanel === tool.tool_key}
                testId={`workspace-tool-${tool.tool_key}`}
                onClick={() => setActivePanel((current) => (current === tool.tool_key ? null : tool.tool_key))}
              />
            ))}
          </>
        ),
      });
    }
    return groups;
  }, [activeExecutionCount, activePanel, extensionTools]);
  const activeExtensionTool = activePanel && activePanel !== 'runs' ? activePanel : null;

  return (
    <AOLRuntimeShellProvider workspaceId={workspaceId} toolGroups={toolGroups}>
      <section
        className="relative h-full min-h-0 min-w-0 flex-1 overflow-hidden bg-white dark:bg-gray-950"
        data-testid="workspace-surface-shell"
        data-active-capability-code={activeCapabilityCode}
        data-surface-path={surfacePath.join('/')}
      >
        <div className="flex h-full min-h-0 min-w-0 overflow-hidden">
          <div className="min-w-0 flex-1 overflow-hidden">
            {children}
          </div>
          {activePanel === 'runs' ? (
            <aside
              className="flex h-full w-80 shrink-0 flex-col border-l border-gray-200 bg-white dark:border-gray-800 dark:bg-gray-950"
              data-testid="workspace-runs-panel"
            >
              <div className="flex h-10 shrink-0 items-center justify-between border-b border-gray-200 px-3 dark:border-gray-800">
                <div className="text-xs font-semibold text-gray-700 dark:text-gray-200">Runs</div>
                <button
                  type="button"
                  aria-label="Close Runs"
                  className="inline-flex h-7 w-7 items-center justify-center rounded text-gray-500 hover:bg-gray-100 hover:text-gray-900 dark:text-gray-400 dark:hover:bg-gray-900 dark:hover:text-gray-100"
                  onClick={() => setActivePanel(null)}
                >
                  <X aria-hidden="true" className="h-4 w-4" />
                </button>
              </div>
              <div className="min-h-0 flex-1 overflow-hidden">
                <WorkspaceRunsPanel
                  workspaceId={workspaceId}
                  activeCapabilityCode={activeCapabilityCode}
                />
              </div>
            </aside>
          ) : null}
          {activeExtensionTool ? (
            <aside
              className="flex h-full w-[360px] shrink-0 flex-col border-l border-gray-200 bg-white dark:border-gray-800 dark:bg-gray-950"
              data-testid="workspace-tool-extension-aside"
            >
              <div className="flex h-10 shrink-0 items-center justify-between border-b border-gray-200 px-3 dark:border-gray-800">
                <div className="text-xs font-semibold text-gray-700 dark:text-gray-200">
                  {extensionTools.find((tool) => tool.tool_key === activeExtensionTool)?.label || 'Tool'}
                </div>
                <button
                  type="button"
                  aria-label="Close Tool"
                  className="inline-flex h-7 w-7 items-center justify-center rounded text-gray-500 hover:bg-gray-100 hover:text-gray-900 dark:text-gray-400 dark:hover:bg-gray-900 dark:hover:text-gray-100"
                  onClick={() => setActivePanel(null)}
                >
                  <X aria-hidden="true" className="h-4 w-4" />
                </button>
              </div>
              <div className="min-h-0 flex-1 overflow-hidden">
                <WorkspaceToolExtensionSlot
                  workspaceId={workspaceId}
                  capabilityCode={activeCapabilityCode}
                  activeToolKey={activeExtensionTool}
                  onActiveToolChange={setActivePanel}
                  onToolsChange={handleExtensionToolsChange}
                />
              </div>
            </aside>
          ) : null}
        </div>
        <WorkspaceToolExtensionSlot
          workspaceId={workspaceId}
          capabilityCode={activeCapabilityCode}
          activeToolKey={null}
          onActiveToolChange={setActivePanel}
          onToolsChange={handleExtensionToolsChange}
        />
      </section>
    </AOLRuntimeShellProvider>
  );
}
