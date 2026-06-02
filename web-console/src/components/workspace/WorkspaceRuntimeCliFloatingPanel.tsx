'use client';

import React, { Suspense } from 'react';

import { WorkspaceFloatingSettingsPanel } from './WorkspaceFloatingSettingsPanel';

const CliApiKeysSection = React.lazy(() => import('@/app/workspaces/[workspaceId]/components/CliApiKeysSection'));

interface WorkspaceRuntimeCliFloatingPanelProps {
  open: boolean;
  workspaceId: string;
  onClose: () => void;
}

export function WorkspaceRuntimeCliFloatingPanel({
  open,
  workspaceId,
  onClose,
}: WorkspaceRuntimeCliFloatingPanelProps) {
  if (!open) {
    return null;
  }

  return (
    <WorkspaceFloatingSettingsPanel
      open={open}
      title="Workspace Runtime CLI"
      closeLabel="Close Runtime CLI"
      onClose={onClose}
    >
      <Suspense fallback={<div className="p-3 text-sm text-gray-500 dark:text-gray-400">Loading Runtime CLI...</div>}>
        <CliApiKeysSection workspaceId={workspaceId} initialAgentTab="codex" />
      </Suspense>
    </WorkspaceFloatingSettingsPanel>
  );
}
