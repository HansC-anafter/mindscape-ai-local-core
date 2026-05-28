'use client';

import React from 'react';
import { Info, PanelRight } from 'lucide-react';

import { AOLRuntimeShellProvider } from '@/components/capabilities/aol-runtime-shell/AOLRuntimeShell';
import { CapabilityWorkbenchInfoPanel } from '@/components/capabilities/workbench/CapabilityWorkbenchInfoPanel';
import {
  CapabilityWorkbenchInfoProvider,
  useCapabilityWorkbenchInfoMetadata,
} from '@/components/capabilities/workbench/CapabilityWorkbenchInfoProvider';
import { getApiBaseUrl } from '@/lib/api-url';
import {
  isPackWorkspaceRailToolVisible,
  normalizeWorkspaceToolContributions,
} from '@/lib/workspace-right-region/workspace-right-region-contract';
import type { WorkspaceToolDefinition } from '@/lib/workspace-tools/workspace-tool-registry';
import WorkspaceRuntimeFrame from '../components/WorkspaceRuntimeFrame';
import {
  useOptionalWorkspaceGlobalToolRail,
  useWorkspaceGlobalToolContributions,
  type WorkspaceGlobalToolContribution,
} from '../components/useWorkspaceGlobalToolRail';
import { useWorkspaceToolDefinitions } from './useWorkspaceToolDefinitions';

const WorkspaceToolExtensionSlot = React.lazy(() => import('./WorkspaceToolExtensionSlot'));

interface WorkspaceSurfaceShellProps {
  workspaceId: string;
  activeCapabilityCode: string;
  surfacePath?: readonly string[];
  children: React.ReactNode;
}

function WorkspaceWorkbenchInfoToolRegistration({
  scopeId,
}: {
  scopeId: string;
}) {
  const metadata = useCapabilityWorkbenchInfoMetadata();
  const contributions = React.useMemo<WorkspaceGlobalToolContribution[]>(() => [
    {
      key: `${scopeId}:workbench-info`,
      id: 'workbench_info',
      label: 'Info',
      icon: <Info aria-hidden="true" className="h-4 w-4" />,
      group: 'workspace',
      order: 5,
      testId: 'workspace-info-tool',
      disabled: !metadata,
      renderPanel: () => (
        metadata ? (
          <CapabilityWorkbenchInfoPanel metadata={metadata} />
        ) : (
          <div
            className="rounded-md border border-dashed border-gray-200 p-3 text-sm text-gray-500 dark:border-gray-800 dark:text-gray-400"
            data-testid="capability-workbench-info-empty"
          >
            No workbench metadata registered.
          </div>
        )
      ),
    },
  ], [metadata, scopeId]);

  useWorkspaceGlobalToolContributions(`${scopeId}:workbench-info`, contributions);

  return null;
}

export default function WorkspaceSurfaceShell({
  workspaceId,
  activeCapabilityCode,
  surfacePath = [],
  children,
}: WorkspaceSurfaceShellProps) {
  return (
    <WorkspaceRuntimeFrame workspaceId={workspaceId} initialLoadProfile="capability-host">
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
  const apiUrl = getApiBaseUrl();
  const rail = useOptionalWorkspaceGlobalToolRail();
  const setActiveCapabilityCode = rail?.setActiveCapabilityCode;
  const workspaceToolDefinitions = useWorkspaceToolDefinitions({
    apiUrl,
    capabilityCode: activeCapabilityCode,
  });
  const extensionTools = React.useMemo<WorkspaceToolDefinition[]>(
    () => workspaceToolDefinitions.tools.filter(isPackWorkspaceRailToolVisible),
    [workspaceToolDefinitions.tools],
  );
  const extensionContributions = React.useMemo(
    () => normalizeWorkspaceToolContributions(extensionTools),
    [extensionTools],
  );
  const globalToolContributions = React.useMemo<WorkspaceGlobalToolContribution[]>(() => extensionContributions.map((tool) => ({
    key: tool.key,
    id: tool.id,
    label: tool.label,
    icon: <PanelRight aria-hidden="true" className="h-4 w-4" />,
    group: tool.group,
    order: tool.order,
    testId: tool.accessibility.test_id,
    renderPanel: () => (
      <WorkspaceToolExtensionSlot
        workspaceId={workspaceId}
        activeToolKey={tool.key}
        tools={extensionTools}
      />
    ),
  })), [extensionContributions, extensionTools, workspaceId]);

  useWorkspaceGlobalToolContributions(
    `workspace-surface:${activeCapabilityCode}`,
    globalToolContributions,
  );

  React.useEffect(() => {
    if (!setActiveCapabilityCode) {
      return undefined;
    }
    setActiveCapabilityCode(activeCapabilityCode);
    return () => {
      setActiveCapabilityCode(null);
    };
  }, [activeCapabilityCode, setActiveCapabilityCode]);

  const contributionScopeId = `workspace-surface:${activeCapabilityCode}`;

  return (
    <AOLRuntimeShellProvider workspaceId={workspaceId}>
      <CapabilityWorkbenchInfoProvider>
        <WorkspaceWorkbenchInfoToolRegistration scopeId={contributionScopeId} />
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
          </div>
        </section>
      </CapabilityWorkbenchInfoProvider>
    </AOLRuntimeShellProvider>
  );
}
