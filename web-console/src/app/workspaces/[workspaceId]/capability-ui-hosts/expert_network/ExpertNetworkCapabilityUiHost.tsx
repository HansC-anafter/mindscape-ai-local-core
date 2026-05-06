'use client';

import CapabilityStaticLoadedComponents, {
  type StaticCapabilityUiHostProps,
} from '../CapabilityStaticLoadedComponents';
import * as ExpertNetworkDashboardModule0 from '@/app/capabilities/expert_network/components/ExpertNetworkDashboard';

const componentModules: Record<string, Record<string, unknown>> = {
  "ExpertNetworkDashboard": ExpertNetworkDashboardModule0 as Record<string, unknown>,
};

export default function ExpertNetworkCapabilityUiHost(props: StaticCapabilityUiHostProps) {
  return (
    <CapabilityStaticLoadedComponents
      {...props}
      componentModules={componentModules}
    />
  );
}
