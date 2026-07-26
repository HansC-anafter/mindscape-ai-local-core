import type { LoadedCapabilityUiCatalog } from './contracts';

const MAX_CACHE_ENTRIES = 32;
const MAX_CACHE_BYTES = 4 * 1024 * 1024;

interface CatalogCacheEntry {
  promise: Promise<LoadedCapabilityUiCatalog>;
  resolved?: LoadedCapabilityUiCatalog;
}

const catalogCache = new Map<string, CatalogCacheEntry>();
let resolvedBytes = 0;

function touch(key: string, entry: CatalogCacheEntry): void {
  catalogCache.delete(key);
  catalogCache.set(key, entry);
}

function evictEntries(): void {
  while (catalogCache.size > MAX_CACHE_ENTRIES) {
    const oldest = catalogCache.entries().next().value as
      | [string, CatalogCacheEntry]
      | undefined;
    if (!oldest) break;
    const [key, entry] = oldest;
    catalogCache.delete(key);
    resolvedBytes -= entry.resolved?.bytes ?? 0;
  }
  while (resolvedBytes > MAX_CACHE_BYTES) {
    const resolvedCandidate = [...catalogCache.entries()].find(
      ([, entry]) => entry.resolved !== undefined,
    );
    if (!resolvedCandidate) break;
    const [key, entry] = resolvedCandidate;
    catalogCache.delete(key);
    resolvedBytes -= entry.resolved?.bytes ?? 0;
  }
}

export function loadCachedCapabilityUiCatalog(
  key: string,
  loader: () => Promise<LoadedCapabilityUiCatalog>,
): Promise<LoadedCapabilityUiCatalog> {
  const cached = catalogCache.get(key);
  if (cached) {
    touch(key, cached);
    return cached.promise;
  }

  const entry: CatalogCacheEntry = {
    promise: Promise.resolve().then(loader),
  };
  entry.promise = entry.promise
    .then((loaded) => {
      const current = catalogCache.get(key);
      if (current === entry) {
        entry.resolved = loaded;
        resolvedBytes += loaded.bytes;
        touch(key, entry);
        evictEntries();
      }
      return loaded;
    })
    .catch((error) => {
      if (catalogCache.get(key) === entry) {
        catalogCache.delete(key);
      }
      throw error;
    });
  catalogCache.set(key, entry);
  evictEntries();
  return entry.promise;
}

export function clearCapabilityUiCatalogCacheForTests(): void {
  catalogCache.clear();
  resolvedBytes = 0;
}

export function capabilityUiCatalogCacheStateForTests(): {
  entries: number;
  bytes: number;
} {
  return {
    entries: catalogCache.size,
    bytes: resolvedBytes,
  };
}
