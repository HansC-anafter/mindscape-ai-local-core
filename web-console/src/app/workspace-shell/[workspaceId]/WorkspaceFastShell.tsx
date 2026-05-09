'use client';

import React, { useEffect, useState } from 'react';
import { getApiBaseUrl } from '@/lib/api-url';
import { buildStaticCapabilityHostPath } from '@/lib/capability-static-hosts';
import { t } from '@/lib/i18n';

interface WorkspaceSummary {
  id: string;
  title: string;
  description?: string | null;
  mode?: string | null;
  execution_mode?: string | null;
  updated_at?: string | null;
}

const API_URL = getApiBaseUrl();

export default function WorkspaceFastShell({ workspaceId }: { workspaceId: string }) {
  const [workspace, setWorkspace] = useState<WorkspaceSummary | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    const controller = new AbortController();

    void fetch(`${API_URL}/api/v1/workspaces/${workspaceId}/summary`, {
      signal: controller.signal,
      cache: 'no-store',
      headers: { Accept: 'application/json' },
    })
      .then(async (response) => {
        if (!response.ok) {
          throw new Error(`Workspace summary failed: ${response.status}`);
        }
        return response.json() as Promise<WorkspaceSummary>;
      })
      .then((data) => {
        if (!cancelled) {
          setWorkspace(data);
          setError(null);
        }
      })
      .catch((err) => {
        if (!cancelled && err.name !== 'AbortError') {
          setError(err instanceof Error ? err.message : String(err));
        }
      });

    return () => {
      cancelled = true;
      controller.abort();
    };
  }, [workspaceId]);

  const instagramWorkbenchPath =
    buildStaticCapabilityHostPath(workspaceId, 'ig') || `/workspaces/${workspaceId}/capability-ui-hosts/ig`;

  const links = [
    { href: instagramWorkbenchPath, label: t('workspaceFastShellInstagramWorkbench') },
    { href: `/workspaces/${workspaceId}/capabilities/performance_direction/start`, label: t('workspaceFastShellPerformanceDirection') },
    { href: `/workspaces/${workspaceId}/executions/timeline`, label: t('workspaceFastShellExecutionTimeline') },
    { href: `/workspaces/${workspaceId}/instruction`, label: t('workspaceFastShellInstructions') },
    { href: `/workspaces/${workspaceId}/meetings`, label: t('workspaceFastShellMeetings') },
  ];

  return (
    <main className="min-h-screen bg-surface dark:bg-gray-950 text-primary dark:text-gray-100">
      <div className="mx-auto flex max-w-5xl flex-col gap-6 px-6 py-8">
        <header className="flex flex-wrap items-start justify-between gap-4 border-b border-default pb-5 dark:border-gray-800">
          <div className="min-w-0">
            <div className="text-xs font-medium uppercase tracking-wide text-tertiary">{t('workspace')}</div>
            <h1 className="mt-2 text-2xl font-semibold">
              {workspace?.title || t('loadingWorkspace')}
            </h1>
            {workspace?.description ? (
              <p className="mt-2 max-w-3xl text-sm text-secondary dark:text-gray-400">
                {workspace.description}
              </p>
            ) : null}
            {error ? (
              <p className="mt-2 text-sm text-red-500 dark:text-red-400">{error}</p>
            ) : null}
          </div>
          <a
            href="/workspaces"
            className="rounded border border-default px-3 py-2 text-sm text-secondary transition-colors hover:bg-surface-secondary dark:border-gray-700 dark:text-gray-300 dark:hover:bg-gray-900"
          >
            {t('navWorkspaces')}
          </a>
        </header>

        <section className="grid gap-3 sm:grid-cols-2">
          {links.map((link) => (
            <a
              key={link.href}
              href={link.href}
              className="rounded border border-default bg-surface-secondary px-4 py-3 text-sm font-medium transition-colors hover:border-accent hover:bg-white dark:border-gray-800 dark:bg-gray-900 dark:hover:border-blue-700 dark:hover:bg-gray-900/70"
            >
              {link.label}
            </a>
          ))}
        </section>

        <section className="rounded border border-default bg-surface-secondary p-4 dark:border-gray-800 dark:bg-gray-900">
          <div className="grid gap-3 text-sm sm:grid-cols-3">
            <div>
              <div className="text-xs uppercase text-tertiary">{t('workspaceMode')}</div>
              <div className="mt-1 font-medium">{workspace?.mode || 'default'}</div>
            </div>
            <div>
              <div className="text-xs uppercase text-tertiary">{t('execution')}</div>
              <div className="mt-1 font-medium">{workspace?.execution_mode || 'hybrid'}</div>
            </div>
            <div>
              <div className="text-xs uppercase text-tertiary">{t('updatedAt')}</div>
              <div className="mt-1 font-medium">{workspace?.updated_at || '-'}</div>
            </div>
          </div>
        </section>
      </div>
    </main>
  );
}
