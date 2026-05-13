'use client';

import React, { useEffect, useState } from 'react';
import { getApiBaseUrl } from '@/lib/api-url';
import CapabilityLoadedComponentsView, {
  buildComponentKey,
  type CapabilityInfo,
  isMainPageComponent,
  type UIComponentInfo,
} from './CapabilityLoadedComponentsView';

interface CapabilityLoadedComponentsProps {
  workspaceId: string;
  capabilityCode: string;
  capabilityInfo: CapabilityInfo | null;
  uiComponents: UIComponentInfo[];
  aolRoutePath?: string;
  surfacePath?: readonly string[];
}

export default function CapabilityLoadedComponents({
  workspaceId,
  capabilityCode,
  capabilityInfo,
  uiComponents,
  aolRoutePath,
  surfacePath = [],
}: CapabilityLoadedComponentsProps) {
  const apiUrl = getApiBaseUrl();
  const [loadedComponents, setLoadedComponents] = useState<Map<string, React.ComponentType<any>>>(new Map());
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;

    const loadComponents = async () => {
      setLoading(true);
      const capabilityId = capabilityInfo?.id || capabilityCode;
      const {
        loadCapabilityUIComponent,
        primeCapabilityUIComponentMetadata,
      } = await import('@/lib/capability-ui-loader');

      if (cancelled) {
        return;
      }

      primeCapabilityUIComponentMetadata(capabilityId, uiComponents);

      const mainPageComponents = uiComponents.filter(isMainPageComponent);
      const otherComponents = uiComponents.filter((component: UIComponentInfo) => !isMainPageComponent(component));
      const componentsToLoad = mainPageComponents.length > 0 ? mainPageComponents : otherComponents;
      const nextLoadedComponents = new Map<string, React.ComponentType<any>>();

      for (const componentInfo of componentsToLoad) {
        try {
          const Component = await loadCapabilityUIComponent(
            capabilityId,
            componentInfo.code,
            apiUrl,
          );

          if (Component) {
            nextLoadedComponents.set(buildComponentKey(capabilityId, componentInfo.code), Component);
          }
        } catch (componentLoadError) {
          console.warn(`Failed to load component ${componentInfo.code}:`, componentLoadError);
        }
      }

      if (!cancelled) {
        setLoadedComponents(nextLoadedComponents);
        setLoading(false);
      }
    };

    void loadComponents();

    return () => {
      cancelled = true;
    };
  }, [apiUrl, capabilityCode, capabilityInfo?.id, uiComponents]);

  return (
    <CapabilityLoadedComponentsView
      workspaceId={workspaceId}
      capabilityCode={capabilityCode}
      capabilityInfo={capabilityInfo}
      uiComponents={uiComponents}
      loadedComponents={loadedComponents}
      loading={loading}
      aolRoutePath={aolRoutePath}
      surfacePath={surfacePath}
    />
  );
}
