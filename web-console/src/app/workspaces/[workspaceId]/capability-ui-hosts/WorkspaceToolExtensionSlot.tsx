'use client';

import React, { useEffect, useState } from 'react';

import { getApiBaseUrl } from '@/lib/api-url';
import type { CapabilityUiLocalizationBridgeV1 } from '@/lib/capability-ui-localization';
import { useLocaleContext } from '@/lib/i18n';
import { loadLocalizedCapabilityUiComponent } from '@/lib/localized-capability-ui-component-loader';
import type { WorkspaceToolDefinition } from '@/lib/workspace-tools/workspace-tool-registry';

interface WorkspaceToolExtensionSlotProps {
  workspaceId: string;
  activeToolKey: string | null;
  tools: WorkspaceToolDefinition[];
}

export default function WorkspaceToolExtensionSlot({
  workspaceId,
  activeToolKey,
  tools,
}: WorkspaceToolExtensionSlotProps) {
  const apiUrl = getApiBaseUrl();
  const { locale } = useLocaleContext();
  const [Component, setComponent] = useState<React.ComponentType<any> | null>(null);
  const [localization, setLocalization] = useState<CapabilityUiLocalizationBridgeV1 | null>(null);
  const activeTool = tools.find((tool) => tool.tool_key === activeToolKey) || null;

  useEffect(() => {
    let cancelled = false;
    setComponent(null);
    setLocalization(null);
    if (!activeTool) {
      return () => {
        cancelled = true;
      };
    }
    void loadLocalizedCapabilityUiComponent({
      apiUrl,
      capabilityCode: activeTool.capability_code,
      componentCode: activeTool.panel_component_code,
      requestedLocale: locale,
      workspaceId,
    }).then((loaded) => {
      if (!cancelled) {
        setComponent(() => loaded?.Component || null);
        setLocalization(loaded?.localization || null);
      }
    }).catch(() => {
      if (!cancelled) {
        setComponent(null);
        setLocalization(null);
      }
    });
    return () => {
      cancelled = true;
    };
  }, [activeTool, apiUrl, locale, tools, workspaceId]);

  return (
    <>
      {activeTool ? (
        <div className="h-full min-h-0" data-testid="workspace-tool-extension-panel">
          {Component ? (
            <Component
              workspaceId={workspaceId}
              apiUrl={apiUrl}
              localization={localization}
            />
          ) : (
            <div className="flex h-full items-center justify-center text-xs text-gray-500 dark:text-gray-400">
              Loading tool...
            </div>
          )}
        </div>
      ) : null}
    </>
  );
}
