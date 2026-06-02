'use client';

import React, { Suspense } from 'react';

import { WorkspaceFloatingSettingsPanel } from './WorkspaceFloatingSettingsPanel';

const RuntimeProfilePanel = React.lazy(() => import('@/app/workspaces/[workspaceId]/components/RuntimeProfilePanel'));

interface WorkspaceRuntimeProfileFloatingPanelProps {
  open: boolean;
  workspaceId: string;
  apiUrl: string;
  onClose: () => void;
}

export function WorkspaceRuntimeProfileFloatingPanel({
  open,
  workspaceId,
  apiUrl,
  onClose,
}: WorkspaceRuntimeProfileFloatingPanelProps) {
  if (!open) {
    return null;
  }

  return (
    <WorkspaceFloatingSettingsPanel
      open={open}
      title="Workspace Runtime Profile"
      closeLabel="Close Runtime Profile"
      onClose={onClose}
    >
      <Suspense fallback={<div className="p-3 text-sm text-gray-500 dark:text-gray-400">Loading Runtime Profile...</div>}>
        <RuntimeProfilePanel workspaceId={workspaceId} apiUrl={apiUrl} />
      </Suspense>
    </WorkspaceFloatingSettingsPanel>
  );
}
