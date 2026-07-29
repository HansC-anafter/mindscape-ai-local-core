import type { CapabilityUiRuntimeLocalizationDescriptor } from './capability-ui-localization';
import type { UIComponentInfo } from './capability-ui-loader-types';

export interface CapabilityUiCapabilityInfo {
  id?: string;
  code?: string;
  display_name?: string;
  version?: string;
  description?: string;
  scope?: string;
  ui_localization?: CapabilityUiRuntimeLocalizationDescriptor;
}

export interface CapabilityUiMetadata {
  capabilityInfo: CapabilityUiCapabilityInfo;
  uiComponents: UIComponentInfo[];
}

type CapabilityUiMetadataCacheEntry = {
  promise?: Promise<CapabilityUiMetadata>;
  metadata?: CapabilityUiMetadata;
  cachedAt?: number;
};

export const CAPABILITY_UI_METADATA_TIMEOUT_MS = 30000;
export const CAPABILITY_UI_METADATA_CACHE_TTL_MS = 2000;

const metadataCache = new Map<string, CapabilityUiMetadataCacheEntry>();

async function fetchJsonWithTimeout<T>(url: string, timeoutMs: number): Promise<T> {
  const controller = new AbortController();
  const timeoutId = globalThis.setTimeout(() => controller.abort(), timeoutMs);
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
    globalThis.clearTimeout(timeoutId);
  }
}

export function isCapabilityUiLoadAbort(error: unknown): boolean {
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

async function loadCapabilityUiMetadata(
  apiUrl: string,
  capabilityCode: string,
  workspaceId: string,
): Promise<CapabilityUiMetadata> {
  const encodedCapabilityCode = encodeURIComponent(capabilityCode);
  const workspaceQuery = `?workspace_id=${encodeURIComponent(workspaceId)}`;
  const [capabilityInfo, uiComponents] = await Promise.all([
    fetchJsonWithTimeout<CapabilityUiCapabilityInfo>(
      `${apiUrl}/api/v1/capability-packs/installed-capabilities/${encodedCapabilityCode}${workspaceQuery}`,
      CAPABILITY_UI_METADATA_TIMEOUT_MS,
    ),
    fetchJsonWithTimeout<UIComponentInfo[]>(
      `${apiUrl}/api/v1/capability-packs/installed-capabilities/${encodedCapabilityCode}/ui-components${workspaceQuery}`,
      CAPABILITY_UI_METADATA_TIMEOUT_MS,
    ),
  ]);
  if (!Array.isArray(uiComponents) || uiComponents.length === 0) {
    throw new Error('capability_ui_components_unavailable');
  }
  return {
    capabilityInfo,
    uiComponents,
  };
}

function capabilityUiMetadataCacheKey(
  apiUrl: string,
  capabilityCode: string,
  workspaceId: string,
): string {
  return `capability-ui-metadata:${apiUrl}:${workspaceId}:${capabilityCode}`;
}

export function isCapabilityUiMetadataFresh(
  entry: CapabilityUiMetadataCacheEntry | undefined,
): boolean {
  return Boolean(
    entry?.metadata
    && typeof entry.cachedAt === 'number'
    && Date.now() - entry.cachedAt <= CAPABILITY_UI_METADATA_CACHE_TTL_MS
  );
}

export function readCapabilityUiMetadataCache(
  apiUrl: string,
  capabilityCode: string,
  workspaceId: string,
): CapabilityUiMetadataCacheEntry | undefined {
  return metadataCache.get(capabilityUiMetadataCacheKey(apiUrl, capabilityCode, workspaceId));
}

export function getCapabilityUiMetadata(
  apiUrl: string,
  capabilityCode: string,
  workspaceId: string,
  options: { forceRefresh?: boolean } = {},
): Promise<CapabilityUiMetadata> {
  const key = capabilityUiMetadataCacheKey(apiUrl, capabilityCode, workspaceId);
  const cached = metadataCache.get(key);
  if (cached?.promise) {
    return cached.promise;
  }
  if (!options.forceRefresh && cached?.metadata && isCapabilityUiMetadataFresh(cached)) {
    return Promise.resolve(cached.metadata);
  }

  let promise: Promise<CapabilityUiMetadata>;
  promise = loadCapabilityUiMetadata(apiUrl, capabilityCode, workspaceId)
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

export function clearCapabilityUiMetadataCacheForTests(): void {
  metadataCache.clear();
}
