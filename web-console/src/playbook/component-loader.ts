/**
 * Playbook Component Loader - Dynamic component loading for playbook UI
 *
 * Loads React components from static file serving endpoints.
 * Components are compiled into JavaScript bundles and served via:
 * /static/capabilities/{capability_code}/ui/components/{componentName}.js
 *
 * Architecture:
 * 1. Components are bundled as UMD modules during capability pack build
 * 2. Bundles are served as static files from backend
 * 3. Frontend dynamically loads bundles using <script> tags
 * 4. Components are registered to window.PlaybookComponents[capabilityCode][componentName]
 */

import type { ComponentType } from 'react';

interface ComponentLoaderOptions {
  capabilityCode: string;
  componentName: string;
  apiUrl?: string;
}

interface LoadedComponent {
  component: ComponentType<any>;
  capabilityCode: string;
  componentName: string;
}

// Cache for loaded components to avoid re-loading
const componentCache = new Map<string, ComponentType<any>>();

// Track loading promises to avoid duplicate loads
const loadingPromises = new Map<string, Promise<ComponentType<any> | null>>();

/**
 * Load a playbook UI component dynamically
 *
 * @param options - Component loading options
 * @param playbookCode - Optional playbook code for registry registration
 * @returns Promise resolving to the React component, or null if not found
 */
export async function loadPlaybookComponent(
  options: ComponentLoaderOptions,
  playbookCode?: string
): Promise<ComponentType<any> | null> {
  const { capabilityCode, componentName, apiUrl = '' } = options;
  const cacheKey = `${capabilityCode}:${componentName}`;

  // Check cache first
  if (componentCache.has(cacheKey)) {
    const cached = componentCache.get(cacheKey)!;
    // Ensure it's registered if we have playbook code
    if (playbookCode && cached) {
      const { getPlaybookRegistry } = await import('./loader');
      const registry = getPlaybookRegistry();
      // Check if already registered
      if (!registry.getComponent(playbookCode, componentName)) {
        registry.registerComponent(playbookCode, componentName, cached);
      }
    }
    return cached;
  }

  // Check if already loading
  if (loadingPromises.has(cacheKey)) {
    return loadingPromises.get(cacheKey)!;
  }

  // Start loading
  const loadPromise = _loadComponentFromStatic(capabilityCode, componentName, apiUrl);
  loadingPromises.set(cacheKey, loadPromise);

  try {
    const component = await loadPromise;
    if (component) {
      componentCache.set(cacheKey, component);
      // Register component to registry after successful load if playbook code is provided
      if (playbookCode) {
        const { getPlaybookRegistry } = await import('./loader');
        const registry = getPlaybookRegistry();
        registry.registerComponent(playbookCode, componentName, component);
      }
    }
    return component;
  } finally {
    loadingPromises.delete(cacheKey);
  }
}

/**
 * Internal function to load component from static file
 *
 * Note: This function does NOT register to registry.
 * Registration is handled by loadPlaybookComponent after successful load.
 */
async function _loadComponentFromStatic(
  capabilityCode: string,
  componentName: string,
  apiUrl: string
): Promise<ComponentType<any> | null> {
  const baseUrl = apiUrl || '';
  const componentUrl = `${baseUrl}/static/capabilities/${capabilityCode}/ui/components/${componentName}.js`;

  try {
    // Check if component is already loaded in window.PlaybookComponents
    if (typeof window !== 'undefined') {
      const globalNamespace = (window as any).PlaybookComponents;
      if (
        globalNamespace &&
        globalNamespace[capabilityCode] &&
        globalNamespace[capabilityCode][componentName]
      ) {
        console.log(
          `Component ${componentName} already loaded for ${capabilityCode}`
        );
        return globalNamespace[capabilityCode][componentName];
      }
    }

    // Try to load from static file first
    try {
      await loadScript(componentUrl);

      // Get component from global namespace
      if (typeof window !== 'undefined') {
        const globalNamespace = (window as any).PlaybookComponents;
        if (
          globalNamespace &&
          globalNamespace[capabilityCode] &&
          globalNamespace[capabilityCode][componentName]
        ) {
          console.log(
            `Successfully loaded component ${componentName} for ${capabilityCode} from static file`
          );
          return globalNamespace[capabilityCode][componentName];
        }
      }
    } catch (staticError) {
      // Fallback to development mode: try to import from source
      console.warn(
        `Failed to load component ${componentName} from static file, trying development mode:`,
        staticError
      );
      return await _loadComponentFromSource(capabilityCode, componentName);
    }

    console.warn(
      `Component ${componentName} not found in global namespace after loading script. Will try dev fallback.`
    );
    // Try dev fallback - this will attempt to load from source files
    return await _loadComponentFromSource(capabilityCode, componentName);
  } catch (error) {
    console.error(
      `Failed to load component ${componentName} for ${capabilityCode}:`,
      error
    );
    // Last resort: try development mode
    return await _loadComponentFromSource(capabilityCode, componentName);
  }
}

/**
 * Development mode: Load component directly from source files
 * This is a fallback for development/testing when bundles are not available
 */
async function _loadComponentFromSource(
  capabilityCode: string,
  componentName: string
): Promise<ComponentType<any> | null> {
  /**
   * NOTE:
   * 這裡原本嘗試用動態 import(`../../app/capabilities/${capabilityCode}/ui/components/${componentName}`)
   * 來做開發模式 fallback，但會讓 webpack/Next 跑出
   * 「Critical dependency: the request of a dependency is an expression」警告。
   *
   * 為了去除警告，取消動態 import 的開發 fallback。若 static bundle 載入失敗，直接返回 null。
   */
  console.warn(
    `Skipping dev-mode source import for ${componentName} (dynamic import disabled to avoid critical dependency warning)`
  );
  return null;
}

/**
 * Load a script dynamically
 */
function loadScript(src: string): Promise<void> {
  return new Promise((resolve, reject) => {
    // Check if script is already loaded
    const existingScript = document.querySelector(`script[src="${src}"]`);
    if (existingScript) {
      resolve();
      return;
    }

    const script = document.createElement('script');
    script.src = src;
    script.async = true;
    script.onload = () => resolve();
    script.onerror = () => reject(new Error(`Failed to load script: ${src}`));
    document.head.appendChild(script);
  });
}

/**
 * Clear component cache (useful for development/reload)
 */
export function clearComponentCache(): void {
  componentCache.clear();
  loadingPromises.clear();
}

/**
 * Preload multiple components
 */
export async function preloadComponents(
  components: ComponentLoaderOptions[]
): Promise<LoadedComponent[]> {
  const loadPromises = components.map(async (options) => {
    const component = await loadPlaybookComponent(options);
    return {
      component: component!,
      capabilityCode: options.capabilityCode,
      componentName: options.componentName,
    };
  });

  const results = await Promise.all(loadPromises);
  return results.filter((r) => r.component !== null) as LoadedComponent[];
}
