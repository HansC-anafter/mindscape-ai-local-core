'use client';

import React, { Suspense } from 'react';

import { WorkspaceFloatingSettingsPanel } from './WorkspaceFloatingSettingsPanel';

const ToolOverlayPanel = React.lazy(() => import('@/app/workspaces/[workspaceId]/components/ToolOverlayPanel'));

interface WorkspaceToolOverlayFloatingPanelProps {
  open: boolean;
  workspaceId: string;
  onClose: () => void;
}

export function WorkspaceToolOverlayFloatingPanel({
  open,
  workspaceId,
  onClose,
}: WorkspaceToolOverlayFloatingPanelProps) {
  if (!open) {
    return null;
  }

  return (
    <WorkspaceFloatingSettingsPanel
      open={open}
      title="Workspace Tool Overlay"
      closeLabel="Close Tool Overlay"
      onClose={onClose}
    >
      <Suspense fallback={<div className="p-3 text-sm text-gray-500 dark:text-gray-400">Loading Tool Overlay...</div>}>
        <ToolOverlayPanel workspaceId={workspaceId} />
      </Suspense>
    </WorkspaceFloatingSettingsPanel>
  );
}
