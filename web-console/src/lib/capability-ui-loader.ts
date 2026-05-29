/**
 * Capability UI Component Loader
 *
 * Boundary Rules:
 * - NO hardcoded Cloud component paths
 * - NO direct imports of Cloud components
 * - Dynamically load components based on API response
 * - Gracefully degrade if component not installed
 */

import { lazy, ComponentType } from 'react';
import * as ReactRuntime from 'react';
import * as ReactDOMRuntime from 'react-dom';
import { convertImportPathToContextKey, normalizeCapabilityContextKey } from './capability-path';
import { loadRegisteredCapabilityComponentsContext } from './capability-ui-context-registry';
import type {
  CapabilityComponentModuleLoad,
  CapabilityComponentsContext,
} from './capability-ui-context-types';

interface UIComponentInfo {
  code: string;
  path: string;
  description: string;
  export: string;
  artifact_types: string[];
  playbook_codes: string[];
  import_path: string;
  asset_url?: string;
  integrity?: string;
  runtime?: string;
  bytes?: number;
  asset_path?: string;
}

declare global {
  // Test-only override so Vitest can short-circuit the webpack-only require.context branch.
  // eslint-disable-next-line no-var
  var __MINDSCAPE_CAPABILITY_UI_TEST_CONTEXT__: CapabilityComponentsContext | undefined;
  // Runtime ESM packs receive React from the host bundle through this bridge.
  // eslint-disable-next-line no-var
  var MindscapeRuntimeReact: {
    React: typeof ReactRuntime;
    ReactDOM: Pick<typeof ReactDOMRuntime, 'flushSync' | 'createPortal'>;
  } | undefined;
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

interface CapabilityComponentsResolver {
  keys: Set<string>;
  load: (key: string) => CapabilityComponentModuleLoad;
  resolve?: (request: string) => string;
  id?: string;
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

export function resetCapabilityUIComponentLoaderCaches(): void {
  componentMetadataCache.clear();
  loadedComponentsCache.clear();
  resolverCache.clear();
}

export function primeCapabilityUIComponentMetadata(
  capabilityCode: string,
  components: UIComponentInfo[] | null | undefined,
): void {
  if (!capabilityCode || !Array.isArray(components)) {
    return;
  }
  const existing = componentMetadataCache.get(capabilityCode) || [];
  const mergedByCode = new Map<string, UIComponentInfo>();
  const previousByCode = new Map<string, UIComponentInfo>();
  for (const component of existing) {
    if (component?.code) {
      mergedByCode.set(component.code, component);
      previousByCode.set(component.code, component);
    }
  }
  for (const component of components) {
    if (component?.code) {
      const previous = previousByCode.get(component.code);
      if (
        previous
        && buildLoadedComponentCacheKey(capabilityCode, component.code, previous)
          !== buildLoadedComponentCacheKey(capabilityCode, component.code, component)
      ) {
        clearLoadedComponentCacheFor(capabilityCode, component.code);
      }
      mergedByCode.set(component.code, component);
    }
  }
  componentMetadataCache.set(capabilityCode, Array.from(mergedByCode.values()));
}

const resolverCache = new Map<string, Promise<CapabilityComponentsResolver | null>>();

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

async function getCapabilityComponentsResolver(
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

function findExistingContextKey(
  candidate: string | null,
  component: UIComponentInfo,
  capabilityCode: string,
  capabilityComponentKeys: Set<string>,
): string | null {
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


/**
 * Cache for component metadata to avoid repeated API calls
 */
const componentMetadataCache = new Map<string, UIComponentInfo[]>();

/**
 * Cache for loaded components to avoid repeated loading.
 *
 * Runtime assets must be keyed by immutable asset identity. A cache keyed only by
 * capability/component keeps serving the old React component after a pack update
 * in an already-open workspace page.
 */
const loadedComponentsCache = new Map<string, ComponentType<any>>();

function buildLoadedComponentCacheKey(
  capabilityCode: string,
  componentCode: string,
  component: UIComponentInfo,
): string {
  const code = capabilityCode.trim();
  const componentId = componentCode.trim();

  if (component.asset_url) {
    return [
      code,
      componentId,
      'runtime',
      component.runtime || '',
      component.asset_url,
      component.integrity || '',
      component.bytes || '',
      component.export || '',
    ].join(':');
  }

  return [
    code,
    componentId,
    'context',
    component.import_path || '',
    component.path || '',
    component.export || '',
  ].join(':');
}

function clearLoadedComponentCacheFor(capabilityCode: string, componentCode: string): void {
  const prefix = `${capabilityCode.trim()}:${componentCode.trim()}:`;
  const legacyKey = `${capabilityCode.trim()}:${componentCode.trim()}`;

  for (const key of Array.from(loadedComponentsCache.keys())) {
    if (key === legacyKey || key.startsWith(prefix)) {
      loadedComponentsCache.delete(key);
    }
  }
}

function ensureRuntimeReactBridge(): void {
  globalThis.MindscapeRuntimeReact = {
    React: ReactRuntime,
    ReactDOM: {
      flushSync: ReactDOMRuntime.flushSync,
      createPortal: ReactDOMRuntime.createPortal,
    },
  };
}

function resolveRuntimeAssetUrl(assetUrl: string, apiUrl: string): string {
  if (/^https?:\/\//.test(assetUrl)) {
    return assetUrl;
  }
  const baseUrl = apiUrl.replace(/\/+$/, '');
  const path = assetUrl.startsWith('/') ? assetUrl : `/${assetUrl}`;
  return `${baseUrl}${path}`;
}

async function sha256Integrity(source: string): Promise<string> {
  if (!globalThis.crypto?.subtle) {
    throw new Error('WebCrypto subtle digest is unavailable');
  }
  const digest = await globalThis.crypto.subtle.digest(
    'SHA-256',
    new TextEncoder().encode(source),
  );
  const bytes = Array.from(new Uint8Array(digest));
  const binary = bytes.map((byte) => String.fromCharCode(byte)).join('');
  return `sha256-${btoa(binary)}`;
}

async function loadRuntimeESMComponent(
  component: UIComponentInfo,
  apiUrl: string,
): Promise<ComponentType<any> | null> {
  if (!component.asset_url) {
    return null;
  }
  if (!component.integrity) {
    console.warn(`[loadCapabilityUIComponent] Runtime asset for ${component.code} missing integrity`);
    return null;
  }
  ensureRuntimeReactBridge();
  const assetUrl = resolveRuntimeAssetUrl(component.asset_url, apiUrl);
  const response = await fetch(assetUrl, { cache: 'force-cache' });
  if (!response.ok) {
    throw new Error(`Runtime asset fetch failed: ${response.status}`);
  }
  const source = await response.text();
  const actualIntegrity = await sha256Integrity(source);
  if (actualIntegrity !== component.integrity) {
    throw new Error(`Runtime asset integrity mismatch for ${component.code}`);
  }
  const blob = new Blob([source], { type: 'text/javascript' });
  const objectUrl = URL.createObjectURL(blob);
  try {
    const module = await import(/* webpackIgnore: true */ objectUrl);
    return module[component.export] || module.default || null;
  } finally {
    URL.revokeObjectURL(objectUrl);
  }
}

/**
 * Load UI component for a capability
 *
 * Boundary: Uses dynamic import with error handling.
 * Component must be installed via CapabilityInstaller, not hardcoded.
 */
export async function loadCapabilityUIComponent(
  capabilityCode: string,
  componentCode: string,
  apiUrl: string
): Promise<ComponentType<any> | null> {
  try {
    // Check metadata cache first to avoid repeated API calls
    let components: UIComponentInfo[];
    if (componentMetadataCache.has(capabilityCode)) {
      components = componentMetadataCache.get(capabilityCode)!;
    } else {
      // Fetch UI component info from API (boundary: no hardcoded paths)
      const response = await fetch(
        `${apiUrl}/api/v1/capability-packs/installed-capabilities/${capabilityCode}/ui-components`
      );

      if (!response.ok) {
        console.warn(`Capability ${capabilityCode} UI components not available`);
        return null;
      }

      components = await response.json();
      if (process.env.NODE_ENV === 'development') {
        const suspicious = components.filter((entry) => {
          const importPath = entry?.import_path;
          const componentPath = entry?.path;
          // Only detect actual pp/src paths, not /app/src (which is normal Docker path)
          const hasSuspiciousPath = (value: unknown) => (
            typeof value === 'string'
            && (
              value.startsWith('pp/src') ||
              value.includes('/pp/src') ||
              value.includes('./pp/src') ||
              (value.includes('pp/src') && !value.includes('/app/'))
            )
          );
          return hasSuspiciousPath(importPath) || hasSuspiciousPath(componentPath);
        });
        if (suspicious.length > 0) {
          console.warn(
            '[capability-ui-loader] Suspicious component paths from API:',
            suspicious.slice(0, 10).map((entry) => ({
              import_path: entry?.import_path,
              path: entry?.path,
            })),
            'total',
            suspicious.length
          );
        }
      }
      // Cache metadata
      componentMetadataCache.set(capabilityCode, components);
    }

    const component = components.find(c => c.code === componentCode);

    if (!component) {
      console.warn(`UI component ${componentCode} not found for capability ${capabilityCode}`);
      return null;
    }

    const cacheKey = buildLoadedComponentCacheKey(capabilityCode, componentCode, component);
    if (loadedComponentsCache.has(cacheKey)) {
      return loadedComponentsCache.get(cacheKey) || null;
    }

    if (component.asset_url) {
      try {
        const RuntimeComponent = await loadRuntimeESMComponent(component, apiUrl);
        if (RuntimeComponent) {
          loadedComponentsCache.set(cacheKey, RuntimeComponent);
          return RuntimeComponent;
        }
      } catch (runtimeImportError) {
        console.error(
          `[loadCapabilityUIComponent] Failed to import runtime UI asset ${component.asset_url}:`,
          runtimeImportError,
        );
        return null;
      }
    }

    const importPath = component.import_path;

    try {
      const rawContextKey = convertImportPathToContextKey(importPath);
      const resolver = await getCapabilityComponentsResolver(capabilityCode);
      if (!resolver) {
        console.warn(
          `[loadCapabilityUIComponent] Capability UI context not registered: ${capabilityCode}`
        );
        return null;
      }

      const contextKey = findExistingContextKey(
        rawContextKey,
        component,
        capabilityCode,
        resolver.keys,
      );
      if (!contextKey) {
        console.error(`[loadCapabilityUIComponent] Invalid import path format: ${importPath}`);
        return null;
      }
      if (!resolver.keys.has(contextKey)) {
        console.warn(
          `[loadCapabilityUIComponent] Context key not found in bundle: ${contextKey} (import_path=${importPath}, component_path=${component.path})`
        );
        return null;
      }

      // Use require.context to load the component (webpack handles this at build time)
      // The context function is created by webpack at build time
      // In 'sync' mode, require.context returns the module directly
      // In 'lazy' mode, it returns a function that returns a Promise
      const moduleLoader = resolver.load(contextKey);

      // Handle both sync and lazy modes
      let module;
      if (typeof moduleLoader === 'function') {
        // Lazy mode: moduleLoader is a function that returns a Promise
        module = await moduleLoader();
      } else if (moduleLoader && typeof moduleLoader.then === 'function') {
        // Promise (shouldn't happen in sync mode, but just in case)
        module = await moduleLoader;
      } else {
        // Sync mode: moduleLoader is the module itself
        module = moduleLoader;
      }

      const Component = module[component.export] || module.default || null;
      if (Component) {
        // Cache the loaded component
        loadedComponentsCache.set(cacheKey, Component);
      } else {
        console.warn(`[loadCapabilityUIComponent] Component ${componentCode} loaded but export '${component.export}' not found. Available exports:`, Object.keys(module));
      }
      return Component;
    } catch (importError) {
      console.error(`[loadCapabilityUIComponent] Failed to import UI component ${componentCode} from ${component.import_path}:`, importError);
      return null;
    }
  } catch (error) {
    console.warn(`Failed to load UI component ${componentCode} for capability ${capabilityCode}:`, error);
    return null;
  }
}

/**
 * Create a lazy-loaded component for a capability UI component
 *
 * Boundary: Component path comes from API, not hardcoded.
 * Returns a component that gracefully degrades if not available.
 */
export function createLazyCapabilityComponent(
  capabilityCode: string,
  componentCode: string,
  apiUrl: string
) {
  return lazy(async () => {
    const Component = await loadCapabilityUIComponent(capabilityCode, componentCode, apiUrl);

    if (!Component) {
      // Return a no-op component if not available (boundary: graceful degradation)
      return { default: (() => null) as ComponentType<any> };
    }

    return { default: Component };
  });
}

/**
 * Check if artifacts match a UI component's criteria
 *
 * Boundary: Generic check, no hardcoded business logic.
 */
export function artifactsMatchComponent(
  artifacts: any[],
  component: UIComponentInfo
): boolean {
  if (!artifacts || artifacts.length === 0) {
    return false;
  }

  // Full-page capability entry points should only render on their dedicated
  // capability routes, not inside artifact preview slots.
  if (
    typeof component?.code === 'string' &&
    (component.code.endsWith('Page') || component.code.endsWith('StudioPage'))
  ) {
    return false;
  }

  // Check artifact types
  if (component.artifact_types && component.artifact_types.length > 0) {
    const hasMatchingType = artifacts.some(artifact =>
      component.artifact_types.includes(artifact.artifact_type)
    );
    if (hasMatchingType) {
      return true;
    }
  }

  // Check playbook codes
  if (component.playbook_codes && component.playbook_codes.length > 0) {
    const hasMatchingPlaybook = artifacts.some(artifact =>
      component.playbook_codes.includes(artifact.playbook_code)
    );
    if (hasMatchingPlaybook) {
      return true;
    }
  }

  return false;
}
