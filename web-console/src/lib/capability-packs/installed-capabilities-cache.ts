export interface InstalledCapability {
  id?: string;
  code?: string;
  display_name?: string;
  version?: string;
  description?: string;
  scope?: string;
  ui_components?: Array<{
    code: string;
    path: string;
    description: string;
    export: string;
    artifact_types: string[];
    playbook_codes: string[];
    import_path: string;
  }>;
}

interface InstalledCapabilitiesCacheEntry {
  expiresAt: number;
  promise: Promise<InstalledCapability[]>;
}

const INSTALLED_CAPABILITIES_TTL_MS = 10 * 60 * 1000;
const installedCapabilitiesCache = new Map<string, InstalledCapabilitiesCacheEntry>();

function cacheKey(apiUrl: string): string {
  return `installed-capabilities:${apiUrl}`;
}

function normalizeInstalledCapabilities(data: unknown): InstalledCapability[] {
  return Array.isArray(data) ? data : [];
}

export function getInstalledCapabilities(apiUrl: string): Promise<InstalledCapability[]> {
  const key = cacheKey(apiUrl);
  const now = Date.now();
  const cached = installedCapabilitiesCache.get(key);
  if (cached && cached.expiresAt > now) {
    return cached.promise;
  }

  const promise = fetch(`${apiUrl}/api/v1/capability-packs/installed-capabilities`, {
    credentials: 'same-origin',
  })
    .then(async (response) => {
      if (!response.ok) {
        return [];
      }
      return normalizeInstalledCapabilities(await response.json());
    })
    .catch((error) => {
      installedCapabilitiesCache.delete(key);
      throw error;
    });

  installedCapabilitiesCache.set(key, {
    expiresAt: now + INSTALLED_CAPABILITIES_TTL_MS,
    promise,
  });
  return promise;
}

export function invalidateInstalledCapabilities(apiUrl: string): void {
  installedCapabilitiesCache.delete(cacheKey(apiUrl));
}
