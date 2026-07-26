'use client';

import { useEffect, useState, type ComponentType } from 'react';
import { useT } from '@/lib/i18n';

type WorkspaceRootClientComponent = ComponentType<{ workspaceId: string }>;

function WorkspacePageLoading() {
  const t = useT();
  return (
    <div className="min-h-screen bg-surface dark:bg-gray-950">
      <div className="flex items-center justify-center h-[calc(100vh-64px)]">
        <div className="text-secondary dark:text-gray-400">{t('loadingWorkspace' as any)}</div>
      </div>
    </div>
  );
}

export default function WorkspacePageClientLoader({ workspaceId }: { workspaceId: string }) {
  const [WorkspaceRootClient, setWorkspaceRootClient] = useState<WorkspaceRootClientComponent | null>(null);
  const [loadError, setLoadError] = useState<Error | null>(null);

  useEffect(() => {
    let cancelled = false;
    void import('./WorkspaceRootClient')
      .then((module) => {
        if (!cancelled) {
          setWorkspaceRootClient(() => module.default);
        }
      })
      .catch((error) => {
        if (!cancelled) {
          console.error('[WorkspacePageClientLoader] Failed to load workspace page:', error);
          setLoadError(error instanceof Error ? error : new Error('Workspace page failed to load'));
        }
      });
    return () => {
      cancelled = true;
    };
  }, []);

  if (loadError) {
    return (
      <div className="min-h-screen bg-surface dark:bg-gray-950">
        <div className="flex items-center justify-center h-[calc(100vh-64px)]">
          <div className="text-red-500 dark:text-red-400">Workspace page failed to load.</div>
        </div>
      </div>
    );
  }

  if (!WorkspaceRootClient) {
    return <WorkspacePageLoading />;
  }

  return <WorkspaceRootClient workspaceId={workspaceId} />;
}
