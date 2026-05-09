import { t } from '@/lib/i18n';
import WorkspacePageClientLoader from './WorkspacePageClientLoader';

export default function WorkspacePage({ params }: { params: { workspaceId?: string } }) {
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

  return <WorkspacePageClientLoader workspaceId={workspaceId} />;
}
