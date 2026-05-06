'use client';

import CapabilityStaticLoadedComponents, {
  type StaticCapabilityUiHostProps,
} from '../CapabilityStaticLoadedComponents';
import * as PublicPersonaStudioPageModule0 from '@/app/capabilities/public_persona_studio/components/PublicPersonaStudioPage';

const componentModules: Record<string, Record<string, unknown>> = {
  "PublicPersonaStudioPage": PublicPersonaStudioPageModule0 as Record<string, unknown>,
};

export default function PublicPersonaStudioCapabilityUiHost(props: StaticCapabilityUiHostProps) {
  return (
    <CapabilityStaticLoadedComponents
      {...props}
      componentModules={componentModules}
    />
  );
}
