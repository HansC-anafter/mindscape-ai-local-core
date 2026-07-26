'use client';

import React, { useEffect, useState } from 'react';
import { getApiBaseUrl } from '@/lib/api-url';
import type { CapabilityUiLocalizationBridgeV1 } from '@/lib/capability-ui-localization';
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
  localizationPromise: Promise<CapabilityUiLocalizationBridgeV1> | null;
}

export default function CapabilityLoadedComponents({
  workspaceId,
  capabilityCode,
  capabilityInfo,
  uiComponents,
  aolRoutePath,
  surfacePath = [],
  localizationPromise,
}: CapabilityLoadedComponentsProps) {
  const apiUrl = getApiBaseUrl();
  const [loadedComponents, setLoadedComponents] = useState<Map<string, React.ComponentType<any>>>(new Map());
  const [loadErrors, setLoadErrors] = useState<Map<string, string>>(new Map());
  const [loading, setLoading] = useState(true);
  const [localization, setLocalization] =
    useState<CapabilityUiLocalizationBridgeV1 | null>(null);

  useEffect(() => {
    let cancelled = false;

    const loadComponents = async () => {
      setLoading(true);
      setLoadErrors(new Map());
      const capabilityId = capabilityInfo?.id || capabilityCode;
      try {
        if (!localizationPromise) {
          throw new Error('Capability UI localization did not start');
        }
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

        const componentLoadPromise = (async () => {
          for (const componentInfo of componentsToLoad) {
            try {
              const Component = await loadCapabilityUIComponent(
                capabilityId,
                componentInfo.code,
                apiUrl,
                workspaceId,
              );

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
          return { nextLoadedComponents, nextLoadErrors };
        })();

        const [nextLocalization] = await Promise.all([
          localizationPromise,
          componentLoadPromise,
        ]);

        if (!cancelled) {
          setLocalization(nextLocalization);
          setLoadedComponents(nextLoadedComponents);
          setLoadErrors(nextLoadErrors);
          setLoading(false);
        }
      } catch (loadError) {
        if (!cancelled) {
          setLocalization(null);
          setLoadedComponents(new Map());
          setLoadErrors(new Map([
            [
              'localization',
              loadError instanceof Error
                ? loadError.message
                : 'Capability UI localization failed',
            ],
          ]));
          setLoading(false);
        }
      }
    };

    void loadComponents();

    return () => {
      cancelled = true;
    };
  }, [apiUrl, capabilityCode, capabilityInfo?.id, localizationPromise, uiComponents, workspaceId]);

  return (
    <CapabilityLoadedComponentsView
      workspaceId={workspaceId}
      capabilityCode={capabilityCode}
      capabilityInfo={capabilityInfo}
      uiComponents={uiComponents}
      loadedComponents={loadedComponents}
      loadErrors={loadErrors}
      loading={loading}
      localization={localization}
      aolRoutePath={aolRoutePath}
      surfacePath={surfacePath}
    />
  );
}
