'use client';

import dynamic from 'next/dynamic';
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
  promise?: Promise<CapabilityUiMetadata>;
  metadata?: CapabilityUiMetadata;
  cachedAt?: number;
};

const CAPABILITY_UI_METADATA_TIMEOUT_MS = 30000;
const CAPABILITY_UI_METADATA_CACHE_TTL_MS = 2000;
const metadataCache = new Map<string, CapabilityUiMetadataCacheEntry>();

function CapabilityUiLoadingState() {
  return (
    <div className="flex h-full w-full min-w-0 items-center justify-center">
      <div className="text-sm text-gray-500 dark:text-gray-400">Loading capability UI...</div>
    </div>
  );
}

const WorkspaceSurfaceShell = dynamic(() => import('./WorkspaceSurfaceShell'), {
  ssr: false,
  loading: CapabilityUiLoadingState,
});
const CapabilityLoadedComponents = dynamic(() => (
  import('../capabilities/[capabilityCode]/CapabilityLoadedComponents')
), {
  ssr: false,
  loading: CapabilityUiLoadingState,
});

async function fetchJsonWithTimeout<T>(url: string, timeoutMs: number): Promise<T> {
  const controller = new AbortController();
  const timeoutId = window.setTimeout(() => controller.abort(), timeoutMs);
  try {
    const response = await fetch(url, {
      credentials: 'same-origin',
      cache: 'no-store',
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

function isCapabilityUiLoadAbort(error: unknown): boolean {
  if (error instanceof DOMException && error.name === 'AbortError') {
    return true;
  }
  if (!(error instanceof Error)) {
    return false;
  }
  const name = error.name.toLowerCase();
  const message = error.message.toLowerCase();
  return name === 'aborterror'
    || message.includes('signal is aborted')
    || message.includes('aborted without reason');
}

function describeCapabilityUiMetadataError(error: unknown): string {
  if (isCapabilityUiLoadAbort(error)) {
    return `Capability UI metadata request timed out after ${Math.round(CAPABILITY_UI_METADATA_TIMEOUT_MS / 1000)} seconds`;
  }
  return error instanceof Error ? error.message : 'Capability UI failed to load';
}

async function loadCapabilityUiMetadata(
  apiUrl: string,
  capabilityCode: string,
): Promise<CapabilityUiMetadata> {
  const encodedCapabilityCode = encodeURIComponent(capabilityCode);
  const capabilityInfoPromise = fetchJsonWithTimeout<CapabilityInfo>(
    `${apiUrl}/api/v1/capability-packs/installed-capabilities/${encodedCapabilityCode}`,
    CAPABILITY_UI_METADATA_TIMEOUT_MS,
  );
  const uiComponentsPromise = fetchJsonWithTimeout<UIComponentInfo[]>(
    `${apiUrl}/api/v1/capability-packs/installed-capabilities/${encodedCapabilityCode}/ui-components`,
    CAPABILITY_UI_METADATA_TIMEOUT_MS,
  );
  const [capabilityInfo, codeUiComponents] = await Promise.all([
    capabilityInfoPromise,
    uiComponentsPromise,
  ]);
  const capabilityId = capabilityInfo.id || capabilityCode;
  const encodedCapabilityId = encodeURIComponent(capabilityId);
  let uiComponents = codeUiComponents;
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

function capabilityUiMetadataCacheKey(apiUrl: string, capabilityCode: string): string {
  return `capability-ui-metadata:${apiUrl}:${capabilityCode}`;
}

function isCapabilityUiMetadataFresh(entry: CapabilityUiMetadataCacheEntry | undefined): boolean {
  return Boolean(
    entry?.metadata
    && typeof entry.cachedAt === 'number'
    && Date.now() - entry.cachedAt <= CAPABILITY_UI_METADATA_CACHE_TTL_MS
  );
}

function readCapabilityUiMetadataCache(
  apiUrl: string,
  capabilityCode: string,
): CapabilityUiMetadataCacheEntry | undefined {
  return metadataCache.get(capabilityUiMetadataCacheKey(apiUrl, capabilityCode));
}

function getCapabilityUiMetadata(
  apiUrl: string,
  capabilityCode: string,
  options: { forceRefresh?: boolean } = {},
): Promise<CapabilityUiMetadata> {
  const key = capabilityUiMetadataCacheKey(apiUrl, capabilityCode);
  const cached = metadataCache.get(key);
  if (cached?.promise) {
    return cached.promise;
  }
  if (!options.forceRefresh && cached?.metadata && isCapabilityUiMetadataFresh(cached)) {
    return Promise.resolve(cached.metadata);
  }

  let promise: Promise<CapabilityUiMetadata>;
  promise = loadCapabilityUiMetadata(apiUrl, capabilityCode)
    .then((nextMetadata) => {
      metadataCache.set(key, {
        metadata: nextMetadata,
        cachedAt: Date.now(),
      });
      return nextMetadata;
    })
    .catch((error) => {
      const latest = metadataCache.get(key);
      if (latest?.promise === promise) {
        if (latest.metadata) {
          metadataCache.set(key, {
            metadata: latest.metadata,
            cachedAt: latest.cachedAt,
          });
        } else {
          metadataCache.delete(key);
        }
      }
      throw error;
    });
  metadataCache.set(key, {
    ...cached,
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
    const cached = readCapabilityUiMetadataCache(apiUrl, capabilityCode);
    const cachedMetadata = cached?.metadata || null;
    const forceRefresh = Boolean(cachedMetadata && !isCapabilityUiMetadataFresh(cached));

    setError(null);
    setMetadata(cachedMetadata);
    void getCapabilityUiMetadata(apiUrl, capabilityCode, { forceRefresh })
      .then((nextMetadata) => {
        if (!cancelled) {
          setMetadata(nextMetadata);
        }
      })
      .catch((metadataError) => {
        if (!cancelled && !cachedMetadata) {
          setError(describeCapabilityUiMetadataError(metadataError));
        }
      });
    return () => {
      cancelled = true;
    };
  }, [apiUrl, capabilityCode]);

  let content: React.ReactNode;
  if (error) {
    content = (
      <div className="flex h-full w-full min-w-0 items-center justify-center p-4">
        <div className="max-w-md text-center">
          <h2 className="mb-2 text-lg font-semibold text-gray-900 dark:text-gray-100">
            Capability UI failed to load
          </h2>
          <div className="mb-4 text-sm text-red-500 dark:text-red-400">{error}</div>
        </div>
      </div>
    );
  } else if (!metadata) {
    content = <CapabilityUiLoadingState />;
  } else {
    content = (
      <CapabilityLoadedComponents
        workspaceId={workspaceId}
        capabilityCode={capabilityCode}
        capabilityInfo={metadata.capabilityInfo}
        uiComponents={metadata.uiComponents}
        surfacePath={surfacePath}
        aolRoutePath={buildCapabilityWorkbenchPath(workspaceId, capabilityCode, { surfacePath })}
      />
    );
  }

  return (
    <React.Suspense fallback={<CapabilityUiLoadingState />}>
      <WorkspaceSurfaceShell
        workspaceId={workspaceId}
        activeCapabilityCode={capabilityCode}
        surfacePath={surfacePath}
      >
        {content}
      </WorkspaceSurfaceShell>
    </React.Suspense>
  );
}
