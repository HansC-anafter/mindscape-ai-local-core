'use client';

import CapabilityStaticLoadedComponents, {
  type StaticCapabilityUiHostProps,
} from '../CapabilityStaticLoadedComponents';
import * as DemoAolPackPageModule0 from '@/app/capabilities/demo_aol_pack/components/DemoAolPackPage';

const componentModules: Record<string, Record<string, unknown>> = {
  "DemoAolPackPage": DemoAolPackPageModule0 as Record<string, unknown>,
};

export default function DemoAolPackCapabilityUiHost(props: StaticCapabilityUiHostProps) {
  return (
    <CapabilityStaticLoadedComponents
      {...props}
      componentModules={componentModules}
    />
  );
}
