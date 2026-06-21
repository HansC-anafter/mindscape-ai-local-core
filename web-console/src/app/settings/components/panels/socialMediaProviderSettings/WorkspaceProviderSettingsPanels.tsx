import React, { Suspense, useMemo } from 'react';

import { createLazySettingsExtensionComponent } from '../../../../../lib/settings-extension-component-loader';
import { API_URL } from './constants';
import type { SettingsExtensionPanel } from './types';

interface WorkspaceProviderSettingsPanelsProps {
  loading: boolean;
  panels: SettingsExtensionPanel[];
  workspaceId?: string;
}

export function WorkspaceProviderSettingsPanels({
  loading,
  panels,
  workspaceId,
}: WorkspaceProviderSettingsPanelsProps) {
  const providerSettingsPanels = useMemo(
    () => panels.map((panel) => ({
      panel,
      LazyComponent: createLazySettingsExtensionComponent(panel, API_URL),
    })),
    [panels],
  );

  return (
    <>
      {loading && (
        <div className="rounded-lg border border-gray-200 p-4 text-sm text-gray-500 dark:border-gray-700 dark:text-gray-400">
          Loading workspace provider settings...
        </div>
      )}

      {providerSettingsPanels.map(({ panel, LazyComponent }) => {
        const props: Record<string, unknown> = {
          apiUrl: API_URL,
        };
        if (panel.requires_workspace_id) {
          props.workspaceId = workspaceId;
        }
        return (
          <div
            key={`${panel.capability_code}:${panel.component_code}`}
            className="rounded-lg border border-gray-200 dark:border-gray-700 p-4"
          >
            <div className="mb-4">
              <h3 className="font-medium text-gray-900 dark:text-gray-100">
                {panel.title}
              </h3>
              {panel.description ? (
                <p className="mt-1 text-sm text-gray-500 dark:text-gray-400">
                  {panel.description}
                </p>
              ) : null}
            </div>
            <Suspense fallback={<div className="text-sm text-gray-500 dark:text-gray-400">Loading {panel.title}...</div>}>
              <LazyComponent {...props} />
            </Suspense>
          </div>
        );
      })}
    </>
  );
}
