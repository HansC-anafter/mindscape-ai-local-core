'use client';

import CapabilitySettingsExtensionSlot from '@/components/capabilities/CapabilitySettingsExtensionSlot';
import { AccessScopeManagementPanel } from '@/components/access/AccessScopeManagementPanel';
import { getApiBaseUrl } from '@/lib/api-url';

export function RemoteWorkbenchAccessSettings() {
  return (
    <div className="space-y-4" data-testid="remote-workbench-access-settings">
      <header>
        <h2 className="text-xl font-semibold text-primary dark:text-gray-100">Accounts &amp; access</h2>
        <p className="mt-1 text-sm text-secondary dark:text-gray-400">
          Manage Local Core accounts and global access. Profiles remain separate personalization data.
        </p>
      </header>
      <div className="rounded-lg border border-default bg-surface p-4 dark:border-gray-700 dark:bg-gray-900">
        <AccessScopeManagementPanel
          apiUrl={getApiBaseUrl()}
          endpoint="/api/v1/access-control/local-core"
          scopeType="local_core"
        />
      </div>
      <div className="rounded-lg border border-default bg-surface dark:border-gray-700 dark:bg-gray-900">
        <div className="border-b border-default p-4 text-sm font-semibold dark:border-gray-700">
          Identity provider diagnostics
        </div>
        <CapabilitySettingsExtensionSlot
          section="remote-workbench-global-access"
          emptyMessage="Install or update Mindscape Cloud Integration to inspect sign-in diagnostics."
          ownerContract={{
            capabilityCode: 'mindscape_cloud_integration',
            componentCode: 'MindscapeRemoteWorkbenchGlobalAdministratorsPanel',
          }}
        />
      </div>
    </div>
  );
}
