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
 * CRITICAL FIX: Use require.context to pre-register all capability components
 * This allows webpack to statically analyze and bundle all components at build time
 * Without this, webpack cannot resolve dynamic string paths in runtime imports
 *
 * NOTE: require.context must be called at module top level, not conditionally
 * Webpack processes this at build time and creates a context function
 */
// @ts-ignore - require.context is a webpack feature, not standard TypeScript
// eslint-disable-next-line @typescript-eslint/no-var-requires
// Use relative path: from src/lib/ to src/app/capabilities = ../app/capabilities
const capabilityComponentsContext = require.context('../app/capabilities', true, /\.tsx$/, 'lazy');

/**
 * Convert import path to require.context key
 * @/app/capabilities/ig/components/IGGridViewModal -> ./ig/components/IGGridViewModal.tsx
 */
function convertImportPathToContextKey(importPath: string): string | null {
  if (!importPath.startsWith('@/app/capabilities/')) {
    return null;
  }
  // Remove @/app/capabilities/ prefix and add .tsx extension
  const relativePath = importPath.replace('@/app/capabilities/', './');
  return `${relativePath}.tsx`;
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
      // Cache metadata
      componentMetadataCache.set(capabilityCode, components);
    }

    const component = components.find(c => c.code === componentCode);

    if (!component) {
      console.warn(`UI component ${componentCode} not found for capability ${capabilityCode}`);
      return null;
    }

    // CRITICAL FIX: Use require.context instead of dynamic import with string path
    // Webpack cannot statically analyze runtime string paths, so we must use require.context
    // which pre-registers all components at build time
    const importPath = component.import_path;

    try {
      console.log(`[loadCapabilityUIComponent] Attempting to import: ${importPath}`);

      // Convert import path to require.context key
      const contextKey = convertImportPathToContextKey(importPath);
      if (!contextKey) {
        console.error(`[loadCapabilityUIComponent] Invalid import path format: ${importPath}`);
        return null;
      }

      console.log(`[loadCapabilityUIComponent] Loading via require.context with key: ${contextKey}`);

      // Use require.context to load the component (webpack handles this at build time)
      // The context function is created by webpack at build time
      // When using 'lazy' mode, require.context returns a function that returns a Promise
      const moduleLoader = capabilityComponentsContext(contextKey);

      // Check if moduleLoader is already a Promise (lazy mode) or a function that returns a Promise
      const module = typeof moduleLoader === 'function'
        ? await moduleLoader()
        : await moduleLoader;

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
      return { default: () => null };
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

