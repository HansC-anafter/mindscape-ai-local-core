'use client';

import React, { useState } from 'react';
import { useParams } from 'next/navigation';
import { t } from '@/lib/i18n';
import { GovernanceTimeline } from './components/GovernanceTimeline';
import { GovernanceMetrics } from './components/GovernanceMetrics';

export default function GovernancePage() {
  const params = useParams();
  const workspaceId = params?.workspaceId as string;
  const [activeTab, setActiveTab] = useState<'timeline' | 'metrics'>('timeline');

  if (!workspaceId) {
    return (
      <div className="p-8 text-center text-secondary dark:text-gray-400">
        {t('workspaceNotFound') || 'Workspace not found'}
      </div>
    );
  }

  return (
    <div className="p-6 max-w-7xl mx-auto">
      <div className="mb-6">
        <h1 className="text-2xl font-bold text-primary dark:text-gray-100 mb-2">
          {t('governance') || 'Governance'}
        </h1>
        <p className="text-sm text-secondary dark:text-gray-400">
          {t('governancePageDescription') || 'View governance decisions and metrics for this workspace'}
        </p>
      </div>

      <div className="border-b border-default dark:border-gray-700 mb-6">
        <nav className="flex gap-4">
          <button
            onClick={() => setActiveTab('timeline')}
            className={`px-4 py-2 text-sm font-medium border-b-2 transition-colors ${
              activeTab === 'timeline'
                ? 'border-blue-600 dark:border-blue-400 text-blue-600 dark:text-blue-400'
                : 'border-transparent text-secondary dark:text-gray-400 hover:text-primary dark:hover:text-gray-100'
            }`}
          >
            {t('decisionHistory') || 'Decision History'}
          </button>
          <button
            onClick={() => setActiveTab('metrics')}
            className={`px-4 py-2 text-sm font-medium border-b-2 transition-colors ${
              activeTab === 'metrics'
                ? 'border-blue-600 dark:border-blue-400 text-blue-600 dark:text-blue-400'
                : 'border-transparent text-secondary dark:text-gray-400 hover:text-primary dark:hover:text-gray-100'
            }`}
          >
            {t('metrics') || 'Metrics'}
          </button>
        </nav>
      </div>

      <div>
        {activeTab === 'timeline' && <GovernanceTimeline workspaceId={workspaceId} />}
        {activeTab === 'metrics' && <GovernanceMetrics workspaceId={workspaceId} />}
      </div>
    </div>
  );
}

