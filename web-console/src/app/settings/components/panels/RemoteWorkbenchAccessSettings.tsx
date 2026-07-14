'use client';

import CapabilitySettingsExtensionSlot from '@/components/capabilities/CapabilitySettingsExtensionSlot';

export function RemoteWorkbenchAccessSettings() {
  return (
    <div className="space-y-4" data-testid="remote-workbench-access-settings">
      <header>
        <h2 className="text-xl font-semibold text-primary dark:text-gray-100">Remote Workbench Access</h2>
        <p className="mt-1 text-sm text-secondary dark:text-gray-400">
          Manage verified Local Core administrators inherited by every current and future workspace.
        </p>
      </header>
      <div className="rounded-lg border border-default bg-surface dark:border-gray-700 dark:bg-gray-900">
        <CapabilitySettingsExtensionSlot
          section="remote-workbench-global-access"
          emptyMessage="Install or update Mindscape Cloud Integration to manage Remote Workbench access."
          ownerContract={{
            capabilityCode: 'mindscape_cloud_integration',
            componentCode: 'MindscapeRemoteWorkbenchGlobalAdministratorsPanel',
          }}
        />
      </div>
    </div>
  );
}
