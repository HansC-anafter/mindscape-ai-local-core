'use client';

import React, { useEffect, useState } from 'react';
import { t } from '@/lib/i18n';

type WorkspacePageClientComponent = React.ComponentType<{ workspaceId: string }>;

export default function WorkspacePageClientLoader({ workspaceId }: { workspaceId: string }) {
  const [ClientComponent, setClientComponent] = useState<WorkspacePageClientComponent | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;

    void import('./WorkspacePageClient')
      .then((module) => {
        if (!cancelled) {
          setClientComponent(() => module.default);
        }
      })
      .catch((error) => {
        if (!cancelled) {
          setLoadError(error instanceof Error ? error.message : String(error));
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
          <div className="text-red-500 dark:text-red-400">{loadError}</div>
        </div>
      </div>
    );
  }

  if (!ClientComponent) {
    return (
      <div className="min-h-screen bg-surface dark:bg-gray-950">
        <div className="flex items-center justify-center h-[calc(100vh-64px)]">
          <div className="text-secondary dark:text-gray-400">{t('loadingWorkspace' as any)}</div>
        </div>
      </div>
    );
  }

  return <ClientComponent workspaceId={workspaceId} />;
}
