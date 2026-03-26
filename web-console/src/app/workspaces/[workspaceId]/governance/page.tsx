'use client';

import React, { useEffect, useState } from 'react';
import { useParams, usePathname, useRouter, useSearchParams } from 'next/navigation';
import { useT } from '@/lib/i18n';
import { GovernanceTimeline } from './components/GovernanceTimeline';
import { GovernanceMetrics } from './components/GovernanceMetrics';
import { GovernedMemoryPanel } from './components/GovernedMemoryPanel';

type GovernanceTabId = 'timeline' | 'metrics' | 'memory';

function resolveTab(value: string | null): GovernanceTabId {
  if (value === 'metrics' || value === 'memory') {
    return value;
  }
  return 'timeline';
}

export default function GovernancePage() {
  const t = useT();
  const params = useParams();
  const router = useRouter();
  const pathname = usePathname();
  const searchParams = useSearchParams();
  const workspaceId = params?.workspaceId as string;
  const [activeTab, setActiveTab] = useState<GovernanceTabId>(
    resolveTab(searchParams?.get('tab') || null)
  );

  useEffect(() => {
    const nextTab = resolveTab(searchParams?.get('tab') || null);
    if (nextTab !== activeTab) {
      setActiveTab(nextTab);
    }
  }, [searchParams, activeTab]);

  const handleTabChange = (tab: GovernanceTabId) => {
    setActiveTab(tab);
    const nextParams = new URLSearchParams(searchParams?.toString() || '');
    if (tab === 'timeline') {
      nextParams.delete('tab');
    } else {
      nextParams.set('tab', tab);
    }
    const nextUrl = nextParams.toString() ? `${pathname}?${nextParams.toString()}` : pathname;
    router.replace(nextUrl, { scroll: false });
  };

  if (!workspaceId) {
    return (
      <div className="p-8 text-center text-secondary dark:text-gray-400">
        {t('workspaceNotFound' as any) || 'Workspace not found'}
      </div>
    );
  }

  return (
    <div className="p-6 max-w-7xl mx-auto">
      <div className="mb-6">
        <h1 className="text-2xl font-bold text-primary dark:text-gray-100 mb-2">
          {t('governance' as any) || 'Governance'}
        </h1>
        <p className="text-sm text-secondary dark:text-gray-400">
          {t('governancePageDescription' as any) || 'Inspect governance decisions, workspace metrics, and governed memory for this workspace.'}
        </p>
      </div>

      <div className="border-b border-default dark:border-gray-700 mb-6">
        <nav className="flex gap-4">
          <button
            onClick={() => handleTabChange('timeline')}
            className={`px-4 py-2 text-sm font-medium border-b-2 transition-colors ${
              activeTab === 'timeline'
                ? 'border-blue-600 dark:border-blue-400 text-blue-600 dark:text-blue-400'
                : 'border-transparent text-secondary dark:text-gray-400 hover:text-primary dark:hover:text-gray-100'
            }`}
          >
            {t('decisionHistory' as any) || 'Decision History'}
          </button>
          <button
            onClick={() => handleTabChange('metrics')}
            className={`px-4 py-2 text-sm font-medium border-b-2 transition-colors ${
              activeTab === 'metrics'
                ? 'border-blue-600 dark:border-blue-400 text-blue-600 dark:text-blue-400'
                : 'border-transparent text-secondary dark:text-gray-400 hover:text-primary dark:hover:text-gray-100'
            }`}
          >
            {t('metrics' as any) || 'Metrics'}
          </button>
          <button
            onClick={() => handleTabChange('memory')}
            className={`px-4 py-2 text-sm font-medium border-b-2 transition-colors ${
              activeTab === 'memory'
                ? 'border-blue-600 dark:border-blue-400 text-blue-600 dark:text-blue-400'
                : 'border-transparent text-secondary dark:text-gray-400 hover:text-primary dark:hover:text-gray-100'
            }`}
          >
            {t('memory' as any) || 'Memory'}
          </button>
        </nav>
      </div>

      <div>
        {activeTab === 'timeline' && <GovernanceTimeline workspaceId={workspaceId} />}
        {activeTab === 'metrics' && <GovernanceMetrics workspaceId={workspaceId} />}
        {activeTab === 'memory' && <GovernedMemoryPanel workspaceId={workspaceId} />}
      </div>
    </div>
  );
}
