'use client';

import React, { Suspense } from 'react';

import { AccessScopeManagementPanel } from '@/components/access/AccessScopeManagementPanel';

const CapabilityExtensionSlot = React.lazy(
  () => import('../../components/CapabilityExtensionSlot'),
);

export function WorkspaceMembersAccessSection({
  workspaceId,
  apiUrl,
}: {
  workspaceId: string;
  apiUrl: string;
}) {
  return (
    <div className="space-y-4" data-testid="workspace-members-access-section">
      <AccessScopeManagementPanel
        apiUrl={apiUrl}
        endpoint={`/api/v1/access-control/workspaces/${encodeURIComponent(workspaceId)}`}
        workspaceId={workspaceId}
        scopeType="workspace"
      />
      <div className="rounded border border-gray-200 p-2 dark:border-gray-700">
        <div className="mb-2 text-xs font-semibold">Remote identity diagnostics</div>
        <Suspense
          fallback={(
            <div role="status" className="text-xs text-gray-500">
              Loading remote identity diagnostics...
            </div>
          )}
        >
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
