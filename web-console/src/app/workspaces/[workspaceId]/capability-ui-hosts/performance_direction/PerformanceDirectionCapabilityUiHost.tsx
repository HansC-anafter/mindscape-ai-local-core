'use client';

import { useMemo, type ComponentType } from 'react';
import dynamic from 'next/dynamic';
import CapabilityLoadedComponentsView, {
  buildComponentKey,
  isMainPageComponent,
  type UIComponentInfo,
} from '../../capabilities/[capabilityCode]/CapabilityLoadedComponentsView';
import type { StaticCapabilityUiHostProps } from '../CapabilityStaticLoadedComponents';

const PERFORMANCE_DIRECTION_EDITOR_CODE = 'PerformanceDirectionStoryboardEditorPage';

const PerformanceDirectionStoryboardEditorPage = dynamic(
  () =>
    import('@/app/capabilities/performance_direction/components/PerformanceDirectionStoryboardEditorPage'),
  {
    ssr: false,
    loading: () => (
      <div className="flex h-full items-center justify-center">
        <div className="text-sm text-gray-500 dark:text-gray-400">Loading PD workbench...</div>
      </div>
    ),
  },
);

function isPerformanceDirectionEditorComponent(component: UIComponentInfo): boolean {
  const path = `${component.path || ''} ${component.import_path || ''}`;
  return (
    component.code === PERFORMANCE_DIRECTION_EDITOR_CODE ||
    component.export === PERFORMANCE_DIRECTION_EDITOR_CODE ||
    path.includes(PERFORMANCE_DIRECTION_EDITOR_CODE)
  );
}

export default function PerformanceDirectionCapabilityUiHost(props: StaticCapabilityUiHostProps) {
  const { capabilityCode, capabilityInfo, uiComponents } = props;
  const loadedComponents = useMemo(() => {
    const capabilityId = capabilityInfo?.id || capabilityCode;
    const mainPageComponents = uiComponents.filter(isMainPageComponent);
    const candidateComponent =
      mainPageComponents.find(isPerformanceDirectionEditorComponent) ||
      uiComponents.find(isPerformanceDirectionEditorComponent) ||
      null;
    const nextLoadedComponents = new Map<string, ComponentType<any>>();

    if (candidateComponent) {
      nextLoadedComponents.set(
        buildComponentKey(capabilityId, candidateComponent.code),
        PerformanceDirectionStoryboardEditorPage,
      );
    }

    return nextLoadedComponents;
  }, [capabilityCode, capabilityInfo?.id, uiComponents]);

  return (
    <CapabilityLoadedComponentsView
      {...props}
      loadedComponents={loadedComponents}
      loading={false}
    />
  );
}
