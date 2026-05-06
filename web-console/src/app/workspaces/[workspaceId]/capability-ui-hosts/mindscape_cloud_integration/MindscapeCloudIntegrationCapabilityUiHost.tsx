'use client';

import CapabilityStaticLoadedComponents, {
  type StaticCapabilityUiHostProps,
} from '../CapabilityStaticLoadedComponents';
import * as MindscapeCloudChannelBindingPanelModule0 from '@/app/capabilities/mindscape_cloud_integration/components/MindscapeCloudChannelBindingPanel';

const componentModules: Record<string, Record<string, unknown>> = {
  "MindscapeCloudChannelBindingPanel": MindscapeCloudChannelBindingPanelModule0 as Record<string, unknown>,
};

export default function MindscapeCloudIntegrationCapabilityUiHost(props: StaticCapabilityUiHostProps) {
  return (
    <CapabilityStaticLoadedComponents
      {...props}
      componentModules={componentModules}
    />
  );
}
