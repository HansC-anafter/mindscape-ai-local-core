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

const componentCache = new Map<string, ComponentType<any>>();

const loadingPromises = new Map<string, Promise<ComponentType<any> | null>>();

export async function loadPlaybookComponent(
  options: ComponentLoaderOptions,
  playbookCode?: string
): Promise<ComponentType<any> | null> {
  const { capabilityCode, componentName, apiUrl = '' } = options;
  const cacheKey = `${capabilityCode}:${componentName}`;

  if (componentCache.has(cacheKey)) {
    const cached = componentCache.get(cacheKey)!;
    if (playbookCode && cached) {
      const { getPlaybookRegistry } = await import('./loader');
      const registry = getPlaybookRegistry();
      if (!registry.getComponent(playbookCode, componentName)) {
        registry.registerComponent(playbookCode, componentName, cached);
      }
    }
    return cached;
  }

  if (loadingPromises.has(cacheKey)) {
    return loadingPromises.get(cacheKey)!;
  }

  const loadPromise = _loadComponentFromStatic(capabilityCode, componentName, apiUrl);
  loadingPromises.set(cacheKey, loadPromise);

  try {
    const component = await loadPromise;
    if (component) {
      componentCache.set(cacheKey, component);
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

async function _loadComponentFromStatic(
  capabilityCode: string,
  componentName: string,
  apiUrl: string
): Promise<ComponentType<any> | null> {
  const baseUrl = apiUrl || '';
  const componentUrl = `${baseUrl}/static/capabilities/${capabilityCode}/ui/components/${componentName}.js`;

  try {
    if (typeof window !== 'undefined') {
      const globalNamespace = (window as any).PlaybookComponents;
      if (
        globalNamespace &&
        globalNamespace[capabilityCode] &&
        globalNamespace[capabilityCode][componentName]
      ) {
        return globalNamespace[capabilityCode][componentName];
      }
    }

    try {
      await loadScript(componentUrl);

      if (typeof window !== 'undefined') {
        const globalNamespace = (window as any).PlaybookComponents;
        if (
          globalNamespace &&
          globalNamespace[capabilityCode] &&
          globalNamespace[capabilityCode][componentName]
        ) {
          return globalNamespace[capabilityCode][componentName];
        }
      }
    } catch {
      return await _loadComponentFromSource(capabilityCode, componentName);
    }

    return await _loadComponentFromSource(capabilityCode, componentName);
  } catch {
    return await _loadComponentFromSource(capabilityCode, componentName);
  }
}

async function _loadComponentFromSource(
  _capabilityCode: string,
  _componentName: string
): Promise<ComponentType<any> | null> {
  return null;
}

function loadScript(src: string): Promise<void> {
  return new Promise((resolve, reject) => {
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

export function clearComponentCache(): void {
  componentCache.clear();
  loadingPromises.clear();
}

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
