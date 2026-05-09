'use client';

import CapabilityStaticLoadedComponents, {
  type StaticCapabilityUiHostProps,
} from '@/app/workspaces/[workspaceId]/capability-ui-hosts/CapabilityStaticLoadedComponents';
import * as IGWorkbenchModule0 from '@/app/capabilities/ig/components/IGWorkbench';

const componentModules: Record<string, Record<string, unknown>> = {
  IGWorkbenchPage: IGWorkbenchModule0 as Record<string, unknown>,
  IGWorkbench: IGWorkbenchModule0 as Record<string, unknown>,
};

export default function IgCapabilityUiHost(props: StaticCapabilityUiHostProps) {
  return (
    <CapabilityStaticLoadedComponents
      {...props}
      componentModules={componentModules}
    />
  );
}
