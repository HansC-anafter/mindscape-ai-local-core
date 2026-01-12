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
import { convertImportPathToContextKey, normalizeCapabilityContextKey } from './capability-path';

interface UIComponentInfo {
  code: string;
  path: string;
  description: string;
  export: string;
  artifact_types: string[];
  playbook_codes: string[];
  import_path: string;
}

/**
 * Pre-register all capability components using require.context
 * Webpack processes this at build time and creates a context function
 */
// @ts-ignore - require.context is a webpack feature, not standard TypeScript
// eslint-disable-next-line @typescript-eslint/no-var-requires
const rawCapabilityComponentsContext = require.context('../app/capabilities', true, /\.tsx$/, 'sync');
const rawKeys = typeof rawCapabilityComponentsContext.keys === 'function'
  ? rawCapabilityComponentsContext.keys()
  : [];
const capabilityComponentKeys = new Set<string>(
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
if (process.env.NODE_ENV === 'development') {
  const suspectKeys = Array.from(capabilityComponentKeys).filter((key) => {
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
      Array.from(capabilityComponentKeys).slice(0, 20)
    );
  } else {
    const sampleKeys = Array.from(capabilityComponentKeys).slice(0, 10);
    console.debug(
      '[capability-ui-loader] Context keys sample (first 10):',
      sampleKeys
    );
  }
}
const capabilityComponentsContext = ((key: string) => {
  let normalizedKey = key;

  if (normalizedKey.startsWith('pp/src/app/capabilities/')) {
    normalizedKey = normalizedKey.replace('pp/src/app/capabilities/', './');
    if (process.env.NODE_ENV === 'development') {
      console.warn('[capability-ui-loader] Fixed pp/src key:', key, '->', normalizedKey);
    }
  } else if (normalizedKey.startsWith('pp/src/')) {
    normalizedKey = normalizedKey.replace('pp/src/', './');
    if (process.env.NODE_ENV === 'development') {
      console.warn('[capability-ui-loader] Fixed pp/src key:', key, '->', normalizedKey);
    }
  } else {
    normalizedKey = normalizeCapabilityContextKey(key) || key;
  }

  const resolvedKey = normalizedKey;

  if (process.env.NODE_ENV === 'development') {
    if (normalizedKey && normalizedKey !== key) {
      console.info('[capability-ui-loader] Normalized context key:', key, '->', normalizedKey);
    }
    if (resolvedKey && !resolvedKey.startsWith('./')) {
      console.warn('[capability-ui-loader] Unexpected context key:', resolvedKey, new Error().stack);
    }
  }

  try {
    return rawCapabilityComponentsContext(resolvedKey);
  } catch (error) {
    if (normalizedKey !== key) {
      if (process.env.NODE_ENV === 'development') {
        console.warn('[capability-ui-loader] Fallback to original context key:', key, error);
      }
      try {
        return rawCapabilityComponentsContext(key);
      } catch (fallbackError) {
        const matchingKey = Array.from(capabilityComponentKeys).find(k =>
          k.endsWith(key.split('/').pop() || '') ||
          k.includes(key.split('/').pop() || '')
        );
        if (matchingKey) {
          console.warn('[capability-ui-loader] Using matching key:', matchingKey, 'for', key);
          return rawCapabilityComponentsContext(matchingKey);
        }
        throw fallbackError;
      }
    }
    throw error;
  }
}) as typeof rawCapabilityComponentsContext;

capabilityComponentsContext.keys = rawCapabilityComponentsContext.keys;
const rawResolve = (rawCapabilityComponentsContext as any).resolve
  ? (rawCapabilityComponentsContext as any).resolve.bind(rawCapabilityComponentsContext)
  : null;
(capabilityComponentsContext as any).resolve = rawResolve
  ? ((request: string) => {
    let normalizedRequest = request;
    if (normalizedRequest.startsWith('pp/src/app/capabilities/')) {
      normalizedRequest = normalizedRequest.replace('pp/src/app/capabilities/', './');
    } else if (normalizedRequest.startsWith('pp/src/')) {
      normalizedRequest = normalizedRequest.replace('pp/src/', './');
    } else {
      normalizedRequest = normalizeCapabilityContextKey(request) || request;
    }
    const resolvedRequest = normalizedRequest;

    if (process.env.NODE_ENV === 'development' && resolvedRequest !== request) {
      console.info('[capability-ui-loader] Resolve normalized:', request, '->', resolvedRequest);
    }

    try {
      return rawResolve(resolvedRequest);
    } catch (error) {
      if (normalizedRequest !== request) {
        if (process.env.NODE_ENV === 'development') {
          console.warn('[capability-ui-loader] resolve fallback to original request:', request, error);
        }
        try {
          return rawResolve(request);
        } catch (fallbackError) {
          throw fallbackError;
        }
      }
      throw error;
    }
  })
  : undefined;
(capabilityComponentsContext as any).id = (rawCapabilityComponentsContext as any).id;

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
  capabilityCode: string
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
 * Cache for loaded components to avoid repeated loading
 */
const loadedComponentsCache = new Map<string, ComponentType<any>>();

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
  // Check cache first
  const cacheKey = `${capabilityCode}:${componentCode}`;
  if (loadedComponentsCache.has(cacheKey)) {
    console.log(`[loadCapabilityUIComponent] Using cached component: ${componentCode}`);
    return loadedComponentsCache.get(cacheKey) || null;
  }

  try {
    // Check metadata cache first to avoid repeated API calls
    let components: UIComponentInfo[];
    if (componentMetadataCache.has(capabilityCode)) {
      components = componentMetadataCache.get(capabilityCode)!;
      console.log(`[loadCapabilityUIComponent] Using cached metadata for capability: ${capabilityCode}`);
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

    const importPath = component.import_path;

    try {
      console.log(`[loadCapabilityUIComponent] Attempting to import path from backend: "${importPath}"`);

      const rawContextKey = convertImportPathToContextKey(importPath);
      const contextKey = findExistingContextKey(rawContextKey, component, capabilityCode);
      console.log(`[loadCapabilityUIComponent] Converted to context key: "${contextKey}"`);
      if (!contextKey) {
        console.error(`[loadCapabilityUIComponent] Invalid import path format: ${importPath}`);
        return null;
      }
      if (!capabilityComponentKeys.has(contextKey)) {
        console.warn(
          `[loadCapabilityUIComponent] Context key not found in bundle: ${contextKey} (import_path=${importPath}, component_path=${component.path})`
        );
        return null;
      }

      console.log(`[loadCapabilityUIComponent] Loading via require.context with key: ${contextKey}`);

      // Use require.context to load the component (webpack handles this at build time)
      // The context function is created by webpack at build time
      // In 'sync' mode, require.context returns the module directly
      // In 'lazy' mode, it returns a function that returns a Promise
      const moduleLoader = capabilityComponentsContext(contextKey);

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
        console.log(`[loadCapabilityUIComponent] Successfully loaded component: ${componentCode}`);
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
