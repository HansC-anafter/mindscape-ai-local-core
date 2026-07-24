import { headers } from 'next/headers';

import { t } from '@/lib/i18n';

import RemoteWorkspaceLanding from './RemoteWorkspaceLanding';

export default async function WorkspacePage({
  params,
  searchParams,
}: {
  params: { workspaceId?: string };
  searchParams?: { active_group_id?: string; topology_revision?: string };
}) {
  const workspaceId = params?.workspaceId;
  if (!workspaceId) {
    return (
      <div className="min-h-screen bg-surface dark:bg-gray-950">
        <div className="flex items-center justify-center h-[calc(100vh-64px)]">
          <div className="text-secondary dark:text-gray-400">{t('workspaceNotFound' as any)}</div>
        </div>
      </div>
    );
  }

  if (headers().get('x-mindscape-remote-ingress') === 'remote_workbench') {
    const topologyRevision = Number(searchParams?.topology_revision);
    return (
      <RemoteWorkspaceLanding
        workspaceId={workspaceId}
        activeGroupId={searchParams?.active_group_id}
        topologyRevision={
          Number.isInteger(topologyRevision) && topologyRevision > 0
            ? topologyRevision
            : undefined
        }
      />
    );
  }

  const { default: WorkspacePageClientLoader } = await import('./WorkspacePageClientLoader');
  return <WorkspacePageClientLoader workspaceId={workspaceId} />;
}
