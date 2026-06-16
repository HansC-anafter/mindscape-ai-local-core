import { convertImportPathToContextKey, normalizeCapabilityContextKey } from './capability-path';
import type {
  CapabilityComponentModuleLoad,
  CapabilityComponentsContext,
} from './capability-ui-context-types';
import type { UIComponentInfo } from './capability-ui-loader-types';

interface CapabilityComponentsResolver {
  keys: Set<string>;
  load: (key: string) => CapabilityComponentModuleLoad;
  resolve?: (request: string) => string;
  id?: string;
}

declare global {
  // Test-only override so Vitest can short-circuit the webpack-only require.context branch.
  // eslint-disable-next-line no-var
  var __MINDSCAPE_CAPABILITY_UI_TEST_CONTEXT__: CapabilityComponentsContext | undefined;
}

const resolverCache = new Map<string, Promise<CapabilityComponentsResolver | null>>();

export function resetCapabilityComponentsResolverCache(): void {
  resolverCache.clear();
}

function normalizeCapabilityComponentKeys(
  rawContext: CapabilityComponentsContext,
): Set<string> {
  const rawKeys = typeof rawContext.keys === 'function' ? rawContext.keys() : [];
  return new Set<string>(
    rawKeys.map((key: string) => {
      if (key.startsWith('pp/src/app/capabilities/')) {
        return key.replace('pp/src/app/capabilities/', './');
      } else if (key.startsWith('pp/src/')) {
        return key.replace('pp/src/', './');
      } else if (!key.startsWith('./')) {
        return key.startsWith('/') ? `.${key}` : `./${key}`;
      }
      return key;
    })
  );
}

function normalizeContextRequest(key: string): string {
  if (key.startsWith('pp/src/app/capabilities/')) {
    return key.replace('pp/src/app/capabilities/', './');
  }
  if (key.startsWith('pp/src/')) {
    return key.replace('pp/src/', './');
  }
  return normalizeCapabilityContextKey(key) || key;
}

function createLegacyResolver(rawContext: CapabilityComponentsContext): CapabilityComponentsResolver {
  const keys = normalizeCapabilityComponentKeys(rawContext);
  const rawResolve = rawContext.resolve ? rawContext.resolve.bind(rawContext) : null;

  return {
    keys,
    id: rawContext.id,
    load: (key: string) => {
      const normalizedKey = normalizeContextRequest(key);

      try {
        return rawContext(normalizedKey);
      } catch (error) {
        if (normalizedKey !== key) {
          try {
            return rawContext(key);
          } catch (fallbackError) {
            const matchingKey = Array.from(keys).find(k =>
              k.endsWith(key.split('/').pop() || '') ||
              k.includes(key.split('/').pop() || '')
            );
            if (matchingKey) {
              return rawContext(matchingKey);
            }
            throw fallbackError;
          }
        }
        throw error;
      }
    },
    resolve: rawResolve
      ? ((request: string) => {
        const normalizedRequest = normalizeContextRequest(request);

        try {
          return rawResolve(normalizedRequest);
        } catch (error) {
          if (normalizedRequest !== request) {
            try {
              return rawResolve(request);
            } catch (fallbackError) {
              throw fallbackError;
            }
          }
          throw error;
        }
      })
      : undefined,
  };
}

function createScopedResolver(
  capabilityCode: string,
  rawContext: CapabilityComponentsContext,
): CapabilityComponentsResolver {
  const rawKeys = typeof rawContext.keys === 'function' ? rawContext.keys() : [];
  const rawByScopedKey = new Map<string, string>();

  for (const rawKey of rawKeys) {
    const normalizedRawKey = normalizeContextRequest(rawKey).replace(/^\.\//, '');
    const scopedKey = normalizeCapabilityContextKey(`./${capabilityCode}/${normalizedRawKey}`);
    if (scopedKey) {
      rawByScopedKey.set(scopedKey, rawKey);
    }
  }

  const keys = new Set(rawByScopedKey.keys());
  const rawResolve = rawContext.resolve ? rawContext.resolve.bind(rawContext) : null;

  return {
    keys,
    id: rawContext.id,
    load: (key: string) => {
      const normalizedKey = normalizeContextRequest(key);
      const rawKey = rawByScopedKey.get(normalizedKey);
      if (rawKey) {
        return rawContext(rawKey);
      }

      const fallbackKey = normalizedKey.replace(new RegExp(`^\\./${capabilityCode.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')}/`), './');
      return rawContext(fallbackKey);
    },
    resolve: rawResolve
      ? ((request: string) => {
        const normalizedRequest = normalizeContextRequest(request);
        const rawKey = rawByScopedKey.get(normalizedRequest);
        return rawResolve(rawKey || normalizedRequest);
      })
      : undefined,
  };
}

function logSuspiciousContextKeys(keys: Set<string>): void {
  if (process.env.NODE_ENV !== 'development') {
    return;
  }

  const suspectKeys = Array.from(keys).filter((key) => {
    return (
      key.startsWith('pp/src') ||
      key.includes('/pp/src') ||
      key.includes('./pp/src') ||
      (key.includes('pp/src') && !key.includes('/app/'))
    );
  });
  if (suspectKeys.length > 0) {
    console.error(
      '[capability-ui-loader] Context keys contain actual pp/src:',
      suspectKeys.slice(0, 10),
      'total',
      suspectKeys.length,
      '\n  All keys sample (first 20):',
      Array.from(keys).slice(0, 20)
    );
  }
}

export async function getCapabilityComponentsResolver(
  capabilityCode: string,
): Promise<CapabilityComponentsResolver | null> {
  const testContext = globalThis.__MINDSCAPE_CAPABILITY_UI_TEST_CONTEXT__;
  if (testContext) {
    const resolver = createLegacyResolver(testContext);
    logSuspiciousContextKeys(resolver.keys);
    return resolver;
  }

  const cacheKey = capabilityCode.trim();
  if (!cacheKey) {
    return null;
  }

  if (!resolverCache.has(cacheKey)) {
    resolverCache.set(cacheKey, (async () => {
      const { loadRegisteredCapabilityComponentsContext } = await import(
        './capability-ui-context-registry'
      );
      const loaded = await loadRegisteredCapabilityComponentsContext(cacheKey);
      if (!loaded) {
        return null;
      }
      const resolver = createScopedResolver(loaded.capabilityCode, loaded.context);
      logSuspiciousContextKeys(resolver.keys);
      return resolver;
    })());
  }

  return resolverCache.get(cacheKey)!;
}

function buildFallbackContextKey(component: UIComponentInfo, capabilityCode: string): string | null {
  if (!component.path) return null;
  let relativePath = component.path.replace(/\\/g, '/');
  if (relativePath.startsWith('ui/')) {
    relativePath = relativePath.slice(3);
  }
  if (!relativePath.includes('/')) {
    relativePath = `components/${relativePath}`;
  }
  if (!/\.(tsx|ts|jsx|js)$/.test(relativePath)) {
    relativePath = `${relativePath}.tsx`;
  }
  return `./${capabilityCode}/${relativePath}`;
}

export function findExistingContextKeyForComponent(
  importPath: string,
  component: UIComponentInfo,
  capabilityCode: string,
  capabilityComponentKeys: Set<string>,
): string | null {
  const candidate = convertImportPathToContextKey(importPath);
  const normalizedCandidate = normalizeCapabilityContextKey(candidate);
  if (normalizedCandidate && capabilityComponentKeys.has(normalizedCandidate)) {
    return normalizedCandidate;
  }

  const fallbackKey = buildFallbackContextKey(component, capabilityCode);
  const variants = new Set([
    capabilityCode,
    capabilityCode.replace(/-/g, '_'),
    capabilityCode.replace(/_/g, '-'),
  ]);

  for (const variant of variants) {
    if (fallbackKey) {
      const variantKey = normalizeCapabilityContextKey(
        fallbackKey.replace(`./${capabilityCode}/`, `./${variant}/`)
      );
      if (variantKey && capabilityComponentKeys.has(variantKey)) {
        return variantKey;
      }
    }
  }

  const fileName = (() => {
    const raw = (component.path || candidate || '').replace(/\\/g, '/');
    if (!raw) return null;
    const name = raw.split('/').pop();
    return name ? name.replace(/\.(tsx|ts|jsx|js)$/, '') : null;
  })();

  if (fileName) {
    for (const key of capabilityComponentKeys) {
      if (key.endsWith(`/${fileName}.tsx`)) {
        for (const variant of variants) {
          if (key.includes(`/${variant}/`)) {
            return key;
          }
        }
      }
    }
  }

  return normalizedCandidate;
}
