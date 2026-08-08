'use client';

import React, { useEffect, useState } from 'react';

import { getApiBaseUrl } from '@/lib/api-url';
import type {
  CapabilityUiLocalizationBridgeV1,
} from '@/lib/capability-ui-localization';
import { useT } from '@/lib/i18n';
import type { WorkspaceToolDefinition } from '@/lib/workspace-tools/workspace-tool-registry';
import { useCapabilityHostLocalizationPromise } from './CapabilityHostLocalizationContext';

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
  const t = useT();
  const activeTool = tools.find((tool) => tool.tool_key === activeToolKey) || null;
  const localizationPromise =
    useCapabilityHostLocalizationPromise(activeTool?.capability_code);
  const [Component, setComponent] = useState<React.ComponentType<any> | null>(null);
  const [localization, setLocalization] =
    useState<CapabilityUiLocalizationBridgeV1 | null>(null);
  const [loadFailed, setLoadFailed] = useState(false);

  useEffect(() => {
    let cancelled = false;
    setComponent(null);
    setLocalization(null);
    setLoadFailed(false);
    if (!activeTool || !localizationPromise) {
      return () => {
        cancelled = true;
      };
    }
    void import('@/lib/capability-ui-loader').then(({
      loadCapabilityUIComponent,
      primeCapabilityUIComponentMetadata,
    }) => {
      if (cancelled) {
        return null;
      }
      primeCapabilityUIComponentMetadata(
        activeTool.capability_code,
        tools.map((tool) => tool.panel_component),
      );
      return Promise.all([
        loadCapabilityUIComponent(
          activeTool.capability_code,
          activeTool.panel_component_code,
          apiUrl,
          workspaceId,
        ),
        localizationPromise,
      ]);
    }).then((loaded) => {
      if (!cancelled) {
        setComponent(() => loaded?.[0] || null);
        setLocalization(loaded?.[1] || null);
      }
    }).catch(() => {
      if (!cancelled) {
        setComponent(null);
        setLocalization(null);
        setLoadFailed(true);
      }
    });
    return () => {
      cancelled = true;
    };
  }, [activeTool, apiUrl, localizationPromise, tools, workspaceId]);

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
          ) : loadFailed ? (
            <div className="flex h-full items-center justify-center text-xs text-red-500 dark:text-red-400">
              {t('workspaceToolLoadFailed')}
            </div>
          ) : (
            <div className="flex h-full items-center justify-center text-xs text-gray-500 dark:text-gray-400">
              {t('workspaceToolLoading')}
            </div>
          )}
        </div>
      ) : null}
    </>
  );
}
