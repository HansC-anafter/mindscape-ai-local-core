'use client';

import React from 'react';
import { useT } from '@/lib/i18n';

interface LeftSidebarTabsProps {
  activeTab: 'timeline' | 'outcomes' | 'background';
  onTabChange: (tab: 'timeline' | 'outcomes' | 'background') => void;
  timelineContent: React.ReactNode;
  outcomesContent: React.ReactNode;
  backgroundContent?: React.ReactNode;
}

export default function LeftSidebarTabs({
  activeTab,
  onTabChange,
  timelineContent,
  outcomesContent,
  backgroundContent
}: LeftSidebarTabsProps) {
  const t = useT();

  return (
    <div className="flex flex-col h-full min-h-0">
      {/* Tab Header */}
      <div className="flex border-b dark:border-gray-700 bg-gray-50 dark:bg-gray-800 shrink-0">
        <button
          onClick={() => onTabChange('timeline')}
          className={`flex-1 px-4 py-2 text-xs font-medium transition-colors ${
            activeTab === 'timeline'
              ? 'bg-white dark:bg-gray-900 text-blue-600 dark:text-blue-400 border-b-2 border-blue-600 dark:border-blue-500'
              : 'text-gray-600 dark:text-gray-400 hover:text-gray-900 dark:hover:text-gray-200 hover:bg-gray-100 dark:hover:bg-gray-700'
          }`}
        >
          {t('tabScheduling') || 'Scheduling'}
        </button>
        <button
          onClick={() => onTabChange('outcomes')}
          className={`flex-1 px-4 py-2 text-xs font-medium transition-colors ${
            activeTab === 'outcomes'
              ? 'bg-white dark:bg-gray-900 text-blue-600 dark:text-blue-400 border-b-2 border-blue-600 dark:border-blue-500'
              : 'text-gray-600 dark:text-gray-400 hover:text-gray-900 dark:hover:text-gray-200 hover:bg-gray-100 dark:hover:bg-gray-700'
          }`}
        >
          {t('tabOutcomes') || 'Outcomes'}
        </button>
        <button
          onClick={() => onTabChange('background')}
          className={`flex-1 px-4 py-2 text-xs font-medium transition-colors ${
            activeTab === 'background'
              ? 'bg-white dark:bg-gray-900 text-blue-600 dark:text-blue-400 border-b-2 border-blue-600 dark:border-blue-500'
              : 'text-gray-600 dark:text-gray-400 hover:text-gray-900 dark:hover:text-gray-200 hover:bg-gray-100 dark:hover:bg-gray-700'
          }`}
        >
          {t('tabBackgroundTasks') || 'Background Tasks'}
        </button>
      </div>

      {/* Tab Content - Scrollable */}
      <div className="flex-1 overflow-hidden min-h-0">
        {activeTab === 'timeline'
          ? timelineContent
          : activeTab === 'outcomes'
          ? outcomesContent
          : backgroundContent || <div className="p-4 text-sm text-gray-500 dark:text-gray-400">{t('backgroundTasksPanel') || 'Background Tasks Panel'}</div>}
      </div>
    </div>
  );
}

