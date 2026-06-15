'use client';

import dynamic from 'next/dynamic';
import Header from '@/components/Header';
import { CAPABILITY_WORKBENCH_VIEWPORT_CLASS } from '@/components/capabilities/workbench/CapabilityWorkbenchResponsiveFrame';
import UpdateBanner from '@/components/sync/UpdateBanner';
import WorkspaceRuntimeFrame from './components/WorkspaceRuntimeFrame';

function WorkspacePageLoading() {
  return (
    <div className="min-h-screen bg-surface dark:bg-gray-950">
      <div className="flex items-center justify-center h-[calc(100vh-64px)]">
        <div className="text-secondary dark:text-gray-400">Loading workspace...</div>
      </div>
    </div>
  );
}

const WorkspacePageClient = dynamic(() => import('./WorkspacePageClient'), {
  ssr: false,
  loading: WorkspacePageLoading,
});

export default function WorkspaceRootClient({ workspaceId }: { workspaceId: string }) {
  return (
    <div className={CAPABILITY_WORKBENCH_VIEWPORT_CLASS}>
      <Header />
      <UpdateBanner clientVersion="1.0.0" />
      <WorkspaceRuntimeFrame workspaceId={workspaceId}>
        <WorkspacePageClient workspaceId={workspaceId} />
      </WorkspaceRuntimeFrame>
    </div>
  );
}
