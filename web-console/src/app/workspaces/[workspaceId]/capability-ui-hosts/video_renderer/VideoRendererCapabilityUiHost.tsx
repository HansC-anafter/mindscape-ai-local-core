'use client';

import CapabilityStaticLoadedComponents, {
  type StaticCapabilityUiHostProps,
} from '../CapabilityStaticLoadedComponents';
import * as RenderQueuePageModule0 from '@/app/capabilities/video_renderer/components/RenderQueuePage';

const componentModules: Record<string, Record<string, unknown>> = {
  "RenderQueuePage": RenderQueuePageModule0 as Record<string, unknown>,
};

export default function VideoRendererCapabilityUiHost(props: StaticCapabilityUiHostProps) {
  return (
    <CapabilityStaticLoadedComponents
      {...props}
      componentModules={componentModules}
    />
  );
}
