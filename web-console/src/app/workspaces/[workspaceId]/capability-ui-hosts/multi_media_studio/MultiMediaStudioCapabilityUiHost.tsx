'use client';

import CapabilityStaticLoadedComponents, {
  type StaticCapabilityUiHostProps,
} from '../CapabilityStaticLoadedComponents';
import * as MultiMediaWorkbenchModule0 from '@/app/capabilities/multi_media_studio/components/MultiMediaWorkbench';

const componentModules: Record<string, Record<string, unknown>> = {
  "MultiMediaWorkbench": MultiMediaWorkbenchModule0 as Record<string, unknown>,
};

export default function MultiMediaStudioCapabilityUiHost(props: StaticCapabilityUiHostProps) {
  return (
    <CapabilityStaticLoadedComponents
      {...props}
      componentModules={componentModules}
    />
  );
}
