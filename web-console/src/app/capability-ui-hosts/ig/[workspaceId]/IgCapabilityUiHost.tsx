'use client';

import dynamic from 'next/dynamic';
import CapabilityStaticLoadedComponents, {
  type StaticCapabilityUiHostProps,
} from '@/app/workspaces/[workspaceId]/capability-ui-hosts/CapabilityStaticLoadedComponents';

const IGWorkbench = dynamic(
  () => import('@/app/capabilities/ig/components/IGWorkbench').then((module) => module.default),
  {
    ssr: false,
    loading: () => (
      <div className="flex h-full items-center justify-center text-sm text-gray-500 dark:text-gray-400">
        Loading Instagram Workbench...
      </div>
    ),
  },
);

const componentModules: Record<string, Record<string, unknown>> = {
  IGWorkbenchPage: { default: IGWorkbench, IGWorkbench },
  IGWorkbench: { default: IGWorkbench, IGWorkbench },
};

export default function IgCapabilityUiHost(props: StaticCapabilityUiHostProps) {
  return (
    <CapabilityStaticLoadedComponents
      {...props}
      componentModules={componentModules}
    />
  );
}
