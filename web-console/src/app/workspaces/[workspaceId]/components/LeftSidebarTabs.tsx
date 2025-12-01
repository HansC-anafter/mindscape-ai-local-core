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
      <div className="flex border-b bg-gray-50 shrink-0">
        <button
          onClick={() => onTabChange('timeline')}
          className={`flex-1 px-4 py-2 text-xs font-medium transition-colors ${
            activeTab === 'timeline'
              ? 'bg-white text-blue-600 border-b-2 border-blue-600'
              : 'text-gray-600 hover:text-gray-900 hover:bg-gray-100'
          }`}
        >
          {t('tabScheduling') || 'Scheduling'}
        </button>
        <button
          onClick={() => onTabChange('outcomes')}
          className={`flex-1 px-4 py-2 text-xs font-medium transition-colors ${
            activeTab === 'outcomes'
              ? 'bg-white text-blue-600 border-b-2 border-blue-600'
              : 'text-gray-600 hover:text-gray-900 hover:bg-gray-100'
          }`}
        >
          {t('tabOutcomes') || 'Outcomes'}
        </button>
        <button
          onClick={() => onTabChange('background')}
          className={`flex-1 px-4 py-2 text-xs font-medium transition-colors ${
            activeTab === 'background'
              ? 'bg-white text-blue-600 border-b-2 border-blue-600'
              : 'text-gray-600 hover:text-gray-900 hover:bg-gray-100'
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
          : backgroundContent || <div className="p-4 text-sm text-gray-500">{t('backgroundTasksPanel') || 'Background Tasks Panel'}</div>}
      </div>
    </div>
  );
}

