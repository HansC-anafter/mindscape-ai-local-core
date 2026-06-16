import type { ComponentType } from 'react';
import type { UIComponentInfo } from './capability-ui-loader-types';

const componentMetadataCache = new Map<string, UIComponentInfo[]>();
const loadedComponentsCache = new Map<string, ComponentType<any>>();

export function clearCapabilityUIComponentCaches(): void {
  componentMetadataCache.clear();
  loadedComponentsCache.clear();
}

export function getCachedMetadata(capabilityCode: string): UIComponentInfo[] | null {
  return componentMetadataCache.get(capabilityCode) || null;
}

export function setCachedMetadata(
  capabilityCode: string,
  components: UIComponentInfo[],
): void {
  componentMetadataCache.set(capabilityCode, components);
}

export function getCachedLoadedComponent(cacheKey: string): ComponentType<any> | null {
  return loadedComponentsCache.get(cacheKey) || null;
}

export function setCachedLoadedComponent(
  cacheKey: string,
  component: ComponentType<any>,
): void {
  loadedComponentsCache.set(cacheKey, component);
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

export function buildLoadedComponentCacheKey(
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
