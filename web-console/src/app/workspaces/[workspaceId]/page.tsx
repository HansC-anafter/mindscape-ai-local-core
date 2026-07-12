import { headers } from 'next/headers';

import { t } from '@/lib/i18n';

import RemoteWorkspaceLanding from './RemoteWorkspaceLanding';

export default async function WorkspacePage({ params }: { params: { workspaceId?: string } }) {
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
    return <RemoteWorkspaceLanding workspaceId={workspaceId} />;
  }

  const { default: WorkspacePageClientLoader } = await import('./WorkspacePageClientLoader');
  return <WorkspacePageClientLoader workspaceId={workspaceId} />;
}
