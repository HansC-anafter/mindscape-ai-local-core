/**
 * Capability UI Component Loader
 *
 * Boundary Rules:
 * - NO hardcoded Cloud component paths
 * - NO direct imports of Cloud components
 * - Dynamically load components based on API response
 * - Gracefully degrade if component not installed
 */

import { lazy, type ComponentType } from 'react';
import {
  buildLoadedComponentCacheKey,
  clearCapabilityUIComponentCaches,
  getCachedLoadedComponent,
  getCachedMetadata,
  primeCapabilityUIComponentMetadata,
  setCachedLoadedComponent,
  setCachedMetadata,
} from './capability-ui-loader-cache';
import {
  findExistingContextKeyForComponent,
  getCapabilityComponentsResolver,
  resetCapabilityComponentsResolverCache,
} from './capability-ui-loader-resolver';
import type { UIComponentInfo } from './capability-ui-loader-types';
import { loadRuntimeESMComponent } from './capability-ui-runtime-assets';

export type { UIComponentInfo } from './capability-ui-loader-types';
export { primeCapabilityUIComponentMetadata } from './capability-ui-loader-cache';

export function resetCapabilityUIComponentLoaderCaches(): void {
  clearCapabilityUIComponentCaches();
  resetCapabilityComponentsResolverCache();
}

function logSuspiciousComponentPaths(components: UIComponentInfo[]): void {
  if (process.env.NODE_ENV !== 'development') {
    return;
  }

  const suspicious = components.filter((entry) => {
    const importPath = entry?.import_path;
    const componentPath = entry?.path;
    const hasSuspiciousPath = (value: unknown) => (
      typeof value === 'string'
      && (
        value.startsWith('pp/src')
        || value.includes('/pp/src')
        || value.includes('./pp/src')
        || (value.includes('pp/src') && !value.includes('/app/'))
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

async function fetchCapabilityUIComponents(
  capabilityCode: string,
  apiUrl: string,
  workspaceId?: string,
): Promise<UIComponentInfo[] | null> {
  const workspaceQuery = workspaceId
    ? `?workspace_id=${encodeURIComponent(workspaceId)}`
    : '';
  const response = await fetch(
    `${apiUrl}/api/v1/capability-packs/installed-capabilities/${capabilityCode}/ui-components${workspaceQuery}`
  );

  if (!response.ok) {
    console.warn(`Capability ${capabilityCode} UI components not available`);
    return null;
  }

  const components = await response.json();
  logSuspiciousComponentPaths(components);
  setCachedMetadata(capabilityCode, components);
  return components;
}

async function loadContextComponent(
  capabilityCode: string,
  componentCode: string,
  component: UIComponentInfo,
  cacheKey: string,
): Promise<ComponentType<any> | null> {
  const importPath = component.import_path;

  try {
    const resolver = await getCapabilityComponentsResolver(capabilityCode);
    if (!resolver) {
      console.warn(
        `[loadCapabilityUIComponent] Capability UI context not registered: ${capabilityCode}`
      );
      return null;
    }

    const contextKey = findExistingContextKeyForComponent(
      importPath,
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

    const moduleLoader = resolver.load(contextKey);

    let loadedModule;
    if (typeof moduleLoader === 'function') {
      loadedModule = await moduleLoader();
    } else if (moduleLoader && typeof (moduleLoader as Promise<unknown>).then === 'function') {
      loadedModule = await moduleLoader;
    } else {
      loadedModule = moduleLoader;
    }

    const Component = loadedModule[component.export] || loadedModule.default || null;
    if (Component) {
      setCachedLoadedComponent(cacheKey, Component);
    } else {
      console.warn(
        `[loadCapabilityUIComponent] Component ${componentCode} loaded but export '${component.export}' not found. Available exports:`,
        Object.keys(loadedModule),
      );
    }
    return Component;
  } catch (importError) {
    console.error(
      `[loadCapabilityUIComponent] Failed to import UI component ${componentCode} from ${component.import_path}:`,
      importError,
    );
    return null;
  }
}

function canUseLegacyContextComponent(component: UIComponentInfo): boolean {
  return component.legacy_context === true || component.runtime === 'legacy_context';
}

/**
 * Load UI component for a capability.
 *
 * Boundary: Uses dynamic import with error handling.
 * Component must be installed via CapabilityInstaller, not hardcoded.
 */
export async function loadCapabilityUIComponent(
  capabilityCode: string,
  componentCode: string,
  apiUrl: string,
  workspaceId?: string,
): Promise<ComponentType<any> | null> {
  try {
    let components = getCachedMetadata(capabilityCode);
    if (!components) {
      components = await fetchCapabilityUIComponents(capabilityCode, apiUrl, workspaceId);
      if (!components) {
        return null;
      }
    }

    const component = components.find(c => c.code === componentCode);
    if (!component) {
      console.warn(`UI component ${componentCode} not found for capability ${capabilityCode}`);
      return null;
    }

    const cacheKey = buildLoadedComponentCacheKey(capabilityCode, componentCode, component);
    const cachedComponent = getCachedLoadedComponent(cacheKey);
    if (cachedComponent) {
      return cachedComponent;
    }

    if (component.asset_url) {
      try {
        const RuntimeComponent = await loadRuntimeESMComponent(component, apiUrl, workspaceId);
        if (RuntimeComponent) {
          setCachedLoadedComponent(cacheKey, RuntimeComponent);
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

    if (!canUseLegacyContextComponent(component)) {
      console.warn(
        `[loadCapabilityUIComponent] Runtime UI metadata for ${capabilityCode}/${componentCode} is missing asset_url and is not marked legacy_context.`
      );
      return null;
    }

    return loadContextComponent(capabilityCode, componentCode, component, cacheKey);
  } catch (error) {
    console.warn(`Failed to load UI component ${componentCode} for capability ${capabilityCode}:`, error);
    return null;
  }
}

/**
 * Create a lazy-loaded component for a capability UI component.
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
      return { default: (() => null) as ComponentType<any> };
    }

    return { default: Component };
  });
}

/**
 * Check if artifacts match a UI component's criteria.
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

  if (
    typeof component?.code === 'string' &&
    (
      component.code.endsWith('Page')
      || component.code.endsWith('StudioPage')
      || component.code.endsWith('Workbench')
    )
  ) {
    return false;
  }

  if (component.artifact_types && component.artifact_types.length > 0) {
    const hasMatchingType = artifacts.some(artifact =>
      component.artifact_types.includes(artifact.artifact_type)
    );
    if (hasMatchingType) {
      return true;
    }
  }

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
