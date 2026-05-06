'use client';

import CapabilityStaticLoadedComponents, {
  type StaticCapabilityUiHostProps,
} from '../CapabilityStaticLoadedComponents';
import * as PracticeCompanionWorkbenchModule0 from '@/app/capabilities/practice_companion/components/PracticeCompanionWorkbench';

const componentModules: Record<string, Record<string, unknown>> = {
  "PracticeCompanionWorkbench": PracticeCompanionWorkbenchModule0 as Record<string, unknown>,
};

export default function PracticeCompanionCapabilityUiHost(props: StaticCapabilityUiHostProps) {
  return (
    <CapabilityStaticLoadedComponents
      {...props}
      componentModules={componentModules}
    />
  );
}
