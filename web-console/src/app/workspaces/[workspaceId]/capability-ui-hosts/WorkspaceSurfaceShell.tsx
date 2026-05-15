'use client';

import React from 'react';
import { Activity, PanelRight, Settings as SettingsIcon, X } from 'lucide-react';

import { AOLRuntimeShellProvider } from '@/components/capabilities/aol-runtime-shell/AOLRuntimeShell';
import {
  WorkspaceToolRailButton,
  type WorkspaceToolRailGroup,
} from '@/components/workspace/WorkspaceToolRail';
import { useWorkspaceDataOptional } from '@/contexts/WorkspaceDataContext';
import { getApiBaseUrl } from '@/lib/api-url';
import {
  WORKSPACE_RIGHT_REGION_PANEL_BODY_CLASS,
  WORKSPACE_RIGHT_REGION_PANEL_WIDTH_CLASS,
  createCoreRightRailContribution,
  isPackWorkspaceRailToolVisible,
  normalizeWorkspaceToolContributions,
} from '@/lib/workspace-right-region/workspace-right-region-contract';
import type { WorkspaceToolDefinition } from '@/lib/workspace-tools/workspace-tool-registry';
import WorkspaceRuntimeFrame from '../components/WorkspaceRuntimeFrame';
import WorkspaceRunsPanel from './WorkspaceRunsPanel';
import WorkspaceToolExtensionSlot from './WorkspaceToolExtensionSlot';

const WorkspaceSettingsToolPanel = React.lazy(() => import('./WorkspaceSettingsToolPanel'));

interface WorkspaceSurfaceShellProps {
  workspaceId: string;
  activeCapabilityCode: string;
  surfacePath?: readonly string[];
  children: React.ReactNode;
}

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
  const apiUrl = getApiBaseUrl();
  const workspaceData = useWorkspaceDataOptional();
  const activeExecutionCount = (workspaceData?.executions || []).filter((execution) => {
    const status = String(execution.status || '').toLowerCase();
    return status === 'running' || status === 'queued' || status === 'pending' || status === 'paused';
  }).length;
  const handleExtensionToolsChange = React.useCallback((tools: WorkspaceToolDefinition[]) => {
    setExtensionTools(tools.filter(isPackWorkspaceRailToolVisible));
  }, []);
  const runsContribution = React.useMemo(() => createCoreRightRailContribution({
    id: 'runs_panel',
    key: 'core:runs_panel',
    label: 'Runs',
    icon: 'Activity',
    order: 10,
    group: 'execution',
    badgeSource: 'active_execution_count',
    testId: 'workspace-runs-tool',
  }), []);
  const settingsContribution = React.useMemo(() => createCoreRightRailContribution({
    id: 'settings',
    key: 'core:settings',
    label: 'Settings',
    icon: 'Settings',
    order: 20,
    group: 'workspace',
    testId: 'workspace-settings-tool',
  }), []);
  const extensionContributions = React.useMemo(
    () => normalizeWorkspaceToolContributions(extensionTools),
    [extensionTools],
  );
  const toolGroups = React.useMemo<WorkspaceToolRailGroup[]>(() => {
    const groups: WorkspaceToolRailGroup[] = [{
      id: 'runs',
      label: 'Runs',
      testId: 'workspace-runs-tool-group',
      children: (
        <WorkspaceToolRailButton
          label={runsContribution.label}
          icon={<Activity aria-hidden="true" className="h-4 w-4" />}
          active={activePanel === runsContribution.key}
          badge={activeExecutionCount || null}
          testId={runsContribution.accessibility.test_id}
          onClick={() => setActivePanel((current) => (current === runsContribution.key ? null : runsContribution.key))}
        />
      ),
    }, {
      id: 'settings',
      label: 'Settings',
      testId: 'workspace-settings-tool-group',
      children: (
        <WorkspaceToolRailButton
          label={settingsContribution.label}
          icon={<SettingsIcon aria-hidden="true" className="h-4 w-4" />}
          active={activePanel === settingsContribution.key}
          testId={settingsContribution.accessibility.test_id}
          onClick={() => setActivePanel((current) => (current === settingsContribution.key ? null : settingsContribution.key))}
        />
      ),
    }];
    if (extensionContributions.length > 0) {
      groups.push({
        id: 'capability-tools',
        label: 'Tools',
        testId: 'workspace-capability-tools-group',
        children: (
          <>
            {extensionContributions.map((tool) => (
              <WorkspaceToolRailButton
                key={tool.key}
                label={tool.label}
                icon={<PanelRight aria-hidden="true" className="h-4 w-4" />}
                active={activePanel === tool.key}
                testId={tool.accessibility.test_id}
                onClick={() => setActivePanel((current) => (current === tool.key ? null : tool.key))}
              />
            ))}
          </>
        ),
      });
    }
    return groups;
  }, [activeExecutionCount, activePanel, extensionContributions, runsContribution, settingsContribution]);
  const activeExtensionTool = activePanel && activePanel !== runsContribution.key && activePanel !== settingsContribution.key
    ? activePanel
    : null;
  const activeExtensionContribution = extensionContributions.find((tool) => tool.key === activeExtensionTool) || null;

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
          {activePanel === runsContribution.key ? (
            <aside
              className={`flex h-full ${WORKSPACE_RIGHT_REGION_PANEL_WIDTH_CLASS} shrink-0 flex-col border-l border-gray-200 bg-white dark:border-gray-800 dark:bg-gray-950`}
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
              <div className={WORKSPACE_RIGHT_REGION_PANEL_BODY_CLASS}>
                <WorkspaceRunsPanel
                  workspaceId={workspaceId}
                  activeCapabilityCode={activeCapabilityCode}
                />
              </div>
            </aside>
          ) : null}
          {activePanel === settingsContribution.key ? (
            <aside
              className={`flex h-full ${WORKSPACE_RIGHT_REGION_PANEL_WIDTH_CLASS} shrink-0 flex-col border-l border-gray-200 bg-white dark:border-gray-800 dark:bg-gray-950`}
              data-testid="workspace-settings-aside"
            >
              <div className="flex h-10 shrink-0 items-center justify-between border-b border-gray-200 px-3 dark:border-gray-800">
                <div className="text-xs font-semibold text-gray-700 dark:text-gray-200">Settings</div>
                <button
                  type="button"
                  aria-label="Close Settings"
                  className="inline-flex h-7 w-7 items-center justify-center rounded text-gray-500 hover:bg-gray-100 hover:text-gray-900 dark:text-gray-400 dark:hover:bg-gray-900 dark:hover:text-gray-100"
                  onClick={() => setActivePanel(null)}
                >
                  <X aria-hidden="true" className="h-4 w-4" />
                </button>
              </div>
              <div className={WORKSPACE_RIGHT_REGION_PANEL_BODY_CLASS}>
                <React.Suspense fallback={<div className="p-3 text-xs text-gray-500 dark:text-gray-400">Loading Settings...</div>}>
                  <WorkspaceSettingsToolPanel workspaceId={workspaceId} apiUrl={apiUrl} />
                </React.Suspense>
              </div>
            </aside>
          ) : null}
          {activeExtensionTool ? (
            <aside
              className={`flex h-full ${WORKSPACE_RIGHT_REGION_PANEL_WIDTH_CLASS} shrink-0 flex-col border-l border-gray-200 bg-white dark:border-gray-800 dark:bg-gray-950`}
              data-testid="workspace-tool-extension-aside"
            >
              <div className="flex h-10 shrink-0 items-center justify-between border-b border-gray-200 px-3 dark:border-gray-800">
                <div className="text-xs font-semibold text-gray-700 dark:text-gray-200">
                  {activeExtensionContribution?.label || 'Tool'}
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
              <div className={WORKSPACE_RIGHT_REGION_PANEL_BODY_CLASS}>
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
