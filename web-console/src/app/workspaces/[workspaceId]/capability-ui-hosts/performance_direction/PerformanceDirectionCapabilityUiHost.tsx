'use client';

import CapabilityStaticLoadedComponents, {
  type StaticCapabilityUiHostProps,
} from '../CapabilityStaticLoadedComponents';
import * as PerformanceDirectionStoryboardEditorPageModule0 from '@/app/capabilities/performance_direction/components/PerformanceDirectionStoryboardEditorPage';

const componentModules: Record<string, Record<string, unknown>> = {
  "PerformanceDirectionStoryboardEditorPage": PerformanceDirectionStoryboardEditorPageModule0 as Record<string, unknown>,
};

export default function PerformanceDirectionCapabilityUiHost(props: StaticCapabilityUiHostProps) {
  return (
    <CapabilityStaticLoadedComponents
      {...props}
      componentModules={componentModules}
    />
  );
}
