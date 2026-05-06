'use client';

import React, { useMemo } from 'react';
import CapabilityLoadedComponentsView, {
  buildComponentKey,
  type CapabilityInfo,
  isMainPageComponent,
  type UIComponentInfo,
} from '../capabilities/[capabilityCode]/CapabilityLoadedComponentsView';

type CapabilityComponentModule = Record<string, unknown>;

export interface StaticCapabilityUiHostProps {
  workspaceId: string;
  capabilityCode: string;
  capabilityInfo: CapabilityInfo | null;
  uiComponents: UIComponentInfo[];
  aolRoutePath?: string;
}

interface CapabilityStaticLoadedComponentsProps extends StaticCapabilityUiHostProps {
  componentModules: Record<string, CapabilityComponentModule>;
}

function componentFileStem(component: UIComponentInfo): string | null {
  const raw = (component.path || component.import_path || '').replace(/\\/g, '/');
  const fileName = raw.split('/').pop();
  return fileName ? fileName.replace(/\.(tsx|ts|jsx|js)$/, '') : null;
}

function resolveStaticComponent(
  component: UIComponentInfo,
  componentModules: Record<string, CapabilityComponentModule>,
): React.ComponentType<any> | null {
  const fileStem = componentFileStem(component);
  const module = componentModules[component.code] || (fileStem ? componentModules[fileStem] : undefined);
  if (!module) {
    return null;
  }

  const exported = module[component.export] || module.default;
  return typeof exported === 'function' ? exported as React.ComponentType<any> : null;
}

export default function CapabilityStaticLoadedComponents({
  workspaceId,
  capabilityCode,
  capabilityInfo,
  uiComponents,
  componentModules,
  aolRoutePath,
}: CapabilityStaticLoadedComponentsProps) {
  const loadedComponents = useMemo(() => {
    const capabilityId = capabilityInfo?.id || capabilityCode;
    const mainPageComponents = uiComponents.filter(isMainPageComponent);
    const otherComponents = uiComponents.filter((component: UIComponentInfo) => !isMainPageComponent(component));
    const componentsToLoad = mainPageComponents.length > 0 ? mainPageComponents : otherComponents;
    const nextLoadedComponents = new Map<string, React.ComponentType<any>>();

    for (const componentInfo of componentsToLoad) {
      const Component = resolveStaticComponent(componentInfo, componentModules);
      if (Component) {
        nextLoadedComponents.set(buildComponentKey(capabilityId, componentInfo.code), Component);
      } else if (process.env.NODE_ENV === 'development') {
        console.warn(
          `[CapabilityStaticLoadedComponents] Static component not registered: ${capabilityCode}:${componentInfo.code}`,
        );
      }
    }

    return nextLoadedComponents;
  }, [capabilityCode, capabilityInfo?.id, componentModules, uiComponents]);

  return (
    <CapabilityLoadedComponentsView
      workspaceId={workspaceId}
      capabilityCode={capabilityCode}
      capabilityInfo={capabilityInfo}
      uiComponents={uiComponents}
      loadedComponents={loadedComponents}
      loading={false}
      aolRoutePath={aolRoutePath}
    />
  );
}
