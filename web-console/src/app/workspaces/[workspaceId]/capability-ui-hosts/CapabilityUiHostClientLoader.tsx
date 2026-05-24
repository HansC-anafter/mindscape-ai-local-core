'use client';

import React from 'react';

import { buildCapabilityWorkbenchPath } from '@/lib/capability-static-hosts';
import { getApiBaseUrl } from '@/lib/api-url';
import type {
  CapabilityInfo,
  UIComponentInfo,
} from '../capabilities/[capabilityCode]/CapabilityLoadedComponentsView';

interface CapabilityUiHostClientLoaderProps {
  workspaceId: string;
  capabilityCode: string;
  surfacePath?: readonly string[];
}

interface CapabilityUiMetadata {
  capabilityInfo: CapabilityInfo;
  uiComponents: UIComponentInfo[];
}

type CapabilityUiMetadataCacheEntry = {
  expiresAt: number;
  promise: Promise<CapabilityUiMetadata>;
};

const CAPABILITY_UI_METADATA_TTL_MS = 10 * 60 * 1000;
const CAPABILITY_UI_METADATA_TIMEOUT_MS = 5000;
const metadataCache = new Map<string, CapabilityUiMetadataCacheEntry>();
const CapabilityLoadedComponents = React.lazy(
  () => import('../capabilities/[capabilityCode]/CapabilityLoadedComponents'),
);

function CapabilityUiLoadingState() {
  return (
    <div className="flex h-full items-center justify-center">
      <div className="text-sm text-gray-500 dark:text-gray-400">Loading capability UI...</div>
    </div>
  );
}

async function fetchJsonWithTimeout<T>(url: string, timeoutMs: number): Promise<T> {
  const controller = new AbortController();
  const timeoutId = window.setTimeout(() => controller.abort(), timeoutMs);
  try {
    const response = await fetch(url, {
      credentials: 'same-origin',
      signal: controller.signal,
    });
    if (!response.ok) {
      throw new Error(`Request failed: ${response.status}`);
    }
    return await response.json() as T;
  } finally {
    window.clearTimeout(timeoutId);
  }
}

async function loadCapabilityUiMetadata(
  apiUrl: string,
  capabilityCode: string,
): Promise<CapabilityUiMetadata> {
  const encodedCapabilityCode = encodeURIComponent(capabilityCode);
  const capabilityInfo = await fetchJsonWithTimeout<CapabilityInfo>(
    `${apiUrl}/api/v1/capability-packs/installed-capabilities/${encodedCapabilityCode}`,
    CAPABILITY_UI_METADATA_TIMEOUT_MS,
  );
  const capabilityId = capabilityInfo.id || capabilityCode;
  const encodedCapabilityId = encodeURIComponent(capabilityId);
  let uiComponents = await fetchJsonWithTimeout<UIComponentInfo[]>(
    `${apiUrl}/api/v1/capability-packs/installed-capabilities/${encodedCapabilityCode}/ui-components`,
    CAPABILITY_UI_METADATA_TIMEOUT_MS,
  );
  if ((!Array.isArray(uiComponents) || uiComponents.length === 0) && capabilityId !== capabilityCode) {
    uiComponents = await fetchJsonWithTimeout<UIComponentInfo[]>(
      `${apiUrl}/api/v1/capability-packs/installed-capabilities/${encodedCapabilityId}/ui-components`,
      CAPABILITY_UI_METADATA_TIMEOUT_MS,
    );
  }
  if (!Array.isArray(uiComponents) || uiComponents.length === 0) {
    throw new Error('No UI components available');
  }
  return {
    capabilityInfo,
    uiComponents,
  };
}

function getCapabilityUiMetadata(
  apiUrl: string,
  capabilityCode: string,
): Promise<CapabilityUiMetadata> {
  const key = `capability-ui-metadata:${capabilityCode}`;
  const now = Date.now();
  const cached = metadataCache.get(key);
  if (cached && cached.expiresAt > now) {
    return cached.promise;
  }
  const promise = loadCapabilityUiMetadata(apiUrl, capabilityCode)
    .catch((error) => {
      metadataCache.delete(key);
      throw error;
    });
  metadataCache.set(key, {
    expiresAt: now + CAPABILITY_UI_METADATA_TTL_MS,
    promise,
  });
  return promise;
}

export default function CapabilityUiHostClientLoader({
  workspaceId,
  capabilityCode,
  surfacePath = [],
}: CapabilityUiHostClientLoaderProps) {
  const apiUrl = getApiBaseUrl();
  const [metadata, setMetadata] = React.useState<CapabilityUiMetadata | null>(null);
  const [error, setError] = React.useState<string | null>(null);

  React.useEffect(() => {
    let cancelled = false;
    setError(null);
    setMetadata(null);
    void getCapabilityUiMetadata(apiUrl, capabilityCode)
      .then((nextMetadata) => {
        if (!cancelled) {
          setMetadata(nextMetadata);
        }
      })
      .catch((metadataError) => {
        if (!cancelled) {
          setError(metadataError instanceof Error ? metadataError.message : 'Capability UI failed to load');
        }
      });
    return () => {
      cancelled = true;
    };
  }, [apiUrl, capabilityCode]);

  if (error) {
    return (
      <div className="flex h-full items-center justify-center p-4">
        <div className="max-w-md text-center">
          <h2 className="mb-2 text-lg font-semibold text-gray-900 dark:text-gray-100">
            Capability UI failed to load
          </h2>
          <div className="mb-4 text-sm text-red-500 dark:text-red-400">{error}</div>
        </div>
      </div>
    );
  }

  if (!metadata) {
    return <CapabilityUiLoadingState />;
  }

  return (
    <React.Suspense fallback={<CapabilityUiLoadingState />}>
      <CapabilityLoadedComponents
        workspaceId={workspaceId}
        capabilityCode={capabilityCode}
        capabilityInfo={metadata.capabilityInfo}
        uiComponents={metadata.uiComponents}
        surfacePath={surfacePath}
        aolRoutePath={buildCapabilityWorkbenchPath(workspaceId, capabilityCode, { surfacePath })}
      />
    </React.Suspense>
  );
}
