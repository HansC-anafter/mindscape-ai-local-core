'use client';

import { useParams } from 'next/navigation';
import { t } from '@/lib/i18n';
import WorkspacePageClient from './WorkspacePageClient';

export default function WorkspacePage() {
  const params = useParams();
  const workspaceId = params?.workspaceId as string | undefined;
  if (!workspaceId) {
    return (
      <div className="min-h-screen bg-surface dark:bg-gray-950">
        <div className="flex items-center justify-center h-[calc(100vh-64px)]">
          <div className="text-secondary dark:text-gray-400">{t('workspaceNotFound' as any)}</div>
        </div>
      </div>
    );
  }

  return <WorkspacePageClient workspaceId={workspaceId} />;
}
