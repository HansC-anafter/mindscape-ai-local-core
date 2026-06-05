'use client';

import React, { useEffect, useState } from 'react';
import { getApiBaseUrl } from '@/lib/api-url';
import CapabilityLoadedComponentsView, {
  buildComponentKey,
  type CapabilityInfo,
  isMainPageComponent,
  type UIComponentInfo,
} from './CapabilityLoadedComponentsView';

const COMPONENT_LOAD_RETRY_DELAY_MS = 250;

function waitForComponentRetry(): Promise<void> {
  return new Promise((resolve) => {
    window.setTimeout(resolve, COMPONENT_LOAD_RETRY_DELAY_MS);
  });
}

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
  const [loadErrors, setLoadErrors] = useState<Map<string, string>>(new Map());
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;

    const loadComponents = async () => {
      setLoading(true);
      setLoadErrors(new Map());
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
      const nextLoadErrors = new Map<string, string>();

      for (const componentInfo of componentsToLoad) {
        try {
          let Component = await loadCapabilityUIComponent(
            capabilityId,
            componentInfo.code,
            apiUrl,
          );
          if (!Component && !cancelled) {
            await waitForComponentRetry();
            Component = await loadCapabilityUIComponent(
              capabilityId,
              componentInfo.code,
              apiUrl,
            );
          }

          if (Component) {
            nextLoadedComponents.set(buildComponentKey(capabilityId, componentInfo.code), Component);
          } else {
            const source = componentInfo.asset_url || componentInfo.import_path || componentInfo.path;
            nextLoadErrors.set(
              componentInfo.code,
              `No React component was resolved from ${source}`,
            );
          }
        } catch (componentLoadError) {
          console.warn(`Failed to load component ${componentInfo.code}:`, componentLoadError);
          nextLoadErrors.set(
            componentInfo.code,
            componentLoadError instanceof Error
              ? componentLoadError.message
              : 'Unknown component load error',
          );
        }
      }

      if (!cancelled) {
        setLoadedComponents(nextLoadedComponents);
        setLoadErrors(nextLoadErrors);
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
      loadErrors={loadErrors}
      loading={loading}
      aolRoutePath={aolRoutePath}
      surfacePath={surfacePath}
    />
  );
}
