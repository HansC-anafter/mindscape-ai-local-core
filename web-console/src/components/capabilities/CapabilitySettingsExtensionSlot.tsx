'use client';

import React, { Suspense, useMemo } from 'react';

import { getApiBaseUrl } from '@/lib/api-url';
import { createLazySettingsExtensionComponent } from '@/lib/settings-extension-component-loader';
import {
  useSettingsExtensionPanels,
  type SettingsExtensionOwnerContract,
} from './useSettingsExtensionPanels';

export type { SettingsExtensionOwnerContract } from './useSettingsExtensionPanels';

interface CapabilitySettingsExtensionSlotProps {
  section: string;
  workspaceId?: string;
  workspaceScopedOnly?: boolean;
  emptyMessage?: string;
  ownerContract?: SettingsExtensionOwnerContract;
}

export default function CapabilitySettingsExtensionSlot({
  section,
  workspaceId,
  workspaceScopedOnly = false,
  emptyMessage,
  ownerContract,
}: CapabilitySettingsExtensionSlotProps) {
  const apiBaseUrl = getApiBaseUrl();
  const { panels, loading, error } = useSettingsExtensionPanels({
    apiBaseUrl,
    section,
    workspaceId,
    workspaceScopedOnly,
    ownerContract,
  });

  const lazyComponents = useMemo(() => panels.map((panel) => ({
    panel,
    LazyComponent: createLazySettingsExtensionComponent(panel, apiBaseUrl, workspaceId),
  })), [apiBaseUrl, panels, workspaceId]);

  if (loading) {
    return (
      <div role="status" aria-live="polite" className="p-3 text-sm text-secondary dark:text-gray-400">
        Loading extension settings...
      </div>
    );
  }
  if (error) {
    return <div role="alert" className="p-3 text-sm text-red-700 dark:text-red-300">{error}</div>;
  }
  if (panels.length === 0) {
    return emptyMessage ? <div className="p-3 text-sm text-secondary dark:text-gray-400">{emptyMessage}</div> : null;
  }

  return (
    <div data-testid={`capability-settings-extension-slot-${section}`}>
      {lazyComponents.map(({ panel, LazyComponent }) => {
        const props: Record<string, unknown> = { apiUrl: apiBaseUrl };
        if (panel.requires_workspace_id && workspaceId) {
          props.workspaceId = workspaceId;
        }
        return (
          <section
            key={`${panel.capability_code}:${panel.component_code}`}
            className="border-t border-default p-3 first:border-t-0 dark:border-gray-700"
          >
            <Suspense fallback={<div role="status" aria-live="polite" className="py-2 text-sm text-gray-500">Loading {panel.title}...</div>}>
              <LazyComponent {...props} />
            </Suspense>
          </section>
        );
      })}
    </div>
  );
}
