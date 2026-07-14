'use client';

import React, { Suspense } from 'react';

const CapabilityExtensionSlot = React.lazy(() => import('../../components/CapabilityExtensionSlot'));

export function WorkspaceRemoteAccessSection({ workspaceId }: { workspaceId: string }) {
  return (
    <div className="space-y-3" data-testid="workspace-settings-remote-access-section">
      <div className="rounded border border-gray-200 p-2 text-xs dark:border-gray-800">
        Review the verified global, direct, and effective Remote Workbench membership for this workspace.
        Global administrator changes are made only in Core Settings.
      </div>
      <div data-testid="workspace-settings-remote-access-extension">
        <Suspense fallback={<div role="status" aria-live="polite" className="p-2 text-xs text-gray-500">Loading Remote Workbench access...</div>}>
          <CapabilityExtensionSlot
            section="remote-workbench-workspace-access"
            workspaceId={workspaceId}
            ownerContract={{
              capabilityCode: 'mindscape_cloud_integration',
              componentCode: 'MindscapeRemoteWorkbenchWorkspaceAccessPanel',
            }}
          />
        </Suspense>
      </div>
    </div>
  );
}
