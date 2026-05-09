'use client';

import React, { useEffect, useState } from 'react';
import { getApiBaseUrl } from '@/lib/api-url';
import { t } from '@/lib/i18n';
import type { CapabilityInfo, UIComponentInfo } from '../../CapabilityLoadedComponentsView';

type CapabilityLoadedComponentsModule = {
  default: React.ComponentType<{
    workspaceId: string;
    capabilityCode: string;
    capabilityInfo: CapabilityInfo | null;
    uiComponents: UIComponentInfo[];
  }>;
};

interface CapabilityUiGenericBootstrapProps {
  workspaceId: string;
  capabilityCode: string;
}

interface LoadedState {
  capabilityInfo: CapabilityInfo | null;
  uiComponents: UIComponentInfo[];
  Component: CapabilityLoadedComponentsModule['default'] | null;
}

async function fetchJson<T>(
  apiUrl: string,
  path: string,
  signal: AbortSignal,
): Promise<{ ok: boolean; status: number; data: T | null }> {
  const response = await fetch(`${apiUrl}${path}`, {
    signal,
    cache: 'no-store',
    headers: { Accept: 'application/json' },
  });

  if (!response.ok) {
    return { ok: false, status: response.status, data: null };
  }

  return { ok: true, status: response.status, data: await response.json() as T };
}

export default function CapabilityUiGenericBootstrap({
  workspaceId,
  capabilityCode,
}: CapabilityUiGenericBootstrapProps) {
  const apiUrl = getApiBaseUrl();
  const [state, setState] = useState<LoadedState>({
    capabilityInfo: null,
    uiComponents: [],
    Component: null,
  });
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    const controller = new AbortController();

    async function loadCapabilityUi() {
      const encodedCapabilityCode = encodeURIComponent(capabilityCode);
      const capabilityResponse = await fetchJson<CapabilityInfo>(
        apiUrl,
        `/api/v1/capability-packs/installed-capabilities/${encodedCapabilityCode}`,
        controller.signal,
      );

      if (!capabilityResponse.ok || !capabilityResponse.data) {
        throw new Error(`${t('failedToLoadWorkspace')}: ${capabilityResponse.status}`);
      }

      const capabilityInfo = capabilityResponse.data;
      const capabilityId = encodeURIComponent(capabilityInfo.id || capabilityCode);
      const componentsResponse = await fetchJson<UIComponentInfo[]>(
        apiUrl,
        `/api/v1/capability-packs/installed-capabilities/${capabilityId}/ui-components`,
        controller.signal,
      );
      const uiComponents = Array.isArray(componentsResponse.data) ? componentsResponse.data : [];

      if (!componentsResponse.ok || uiComponents.length === 0) {
        throw new Error(`${t('failedToLoadWorkspace')}: ${componentsResponse.status}`);
      }

      const loadedModule = await import('../../CapabilityLoadedComponents') as CapabilityLoadedComponentsModule;

      if (!cancelled) {
        setState({
          capabilityInfo,
          uiComponents,
          Component: loadedModule.default,
        });
        setError(null);
      }
    }

    void loadCapabilityUi().catch((err) => {
      if (!cancelled && err.name !== 'AbortError') {
        setError(err instanceof Error ? err.message : String(err));
      }
    });

    return () => {
      cancelled = true;
      controller.abort();
    };
  }, [apiUrl, capabilityCode]);

  if (error) {
    return (
      <div className="flex h-full flex-col items-center justify-center p-4">
        <div className="max-w-md text-center">
          <h2 className="mb-2 text-lg font-semibold text-gray-900 dark:text-gray-100">
            {t('errorLoadingWorkspace')}
          </h2>
          <div className="mb-4 text-sm text-red-500 dark:text-red-400">{error}</div>
          <a
            href={`/workspaces/${workspaceId}/capabilities/${capabilityCode}`}
            className="inline-flex rounded bg-gray-200 px-4 py-2 text-sm text-gray-700 transition-colors hover:bg-gray-300 dark:bg-gray-700 dark:text-gray-300 dark:hover:bg-gray-600"
          >
            {t('back')}
          </a>
        </div>
      </div>
    );
  }

  const LoadedComponent = state.Component;
  if (!LoadedComponent) {
    return (
      <div className="flex h-full items-center justify-center">
        <div className="text-sm text-gray-500 dark:text-gray-400">{t('loadingWorkspace')}</div>
      </div>
    );
  }

  return (
    <LoadedComponent
      workspaceId={workspaceId}
      capabilityCode={capabilityCode}
      capabilityInfo={state.capabilityInfo}
      uiComponents={state.uiComponents}
    />
  );
}
