'use client';

import React from 'react';
import { useT } from '@/lib/i18n';

interface TabConfig {
  key: 'timeline' | 'outcomes' | 'background';
  label: string;
  subtitle: string;
}

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

  const tabs: TabConfig[] = [
    { key: 'timeline', label: t('tabScheduling') || 'Scheduling', subtitle: t('tabSchedulingSubtitle') || 'Tasks & Execution' },
    { key: 'outcomes', label: t('tabOutcomes') || 'Outcomes', subtitle: t('tabOutcomesSubtitle') || 'Output Overview' },
    { key: 'background', label: t('tabBackgroundTasks') || 'Thinking', subtitle: t('tabBackgroundTasksSubtitle') || 'Outline & Strategy' },
  ];

  return (
    <div className="flex flex-col h-full min-h-0">
      {/* Tab Header */}
      <div className="flex border-b dark:border-gray-700 bg-gray-50 dark:bg-gray-800 shrink-0">
        {tabs.map((tab) => (
          <button
            key={tab.key}
            onClick={() => onTabChange(tab.key)}
            className={`flex-1 px-4 py-2 text-xs font-medium transition-colors flex flex-col items-center ${
              activeTab === tab.key
                ? 'bg-white dark:bg-gray-900 text-blue-600 dark:text-blue-400 border-b-2 border-blue-600 dark:border-blue-500'
                : 'text-gray-600 dark:text-gray-400 hover:text-gray-900 dark:hover:text-gray-200 hover:bg-gray-100 dark:hover:bg-gray-700'
            }`}
          >
            <span className="tab-label">{tab.label}</span>
            <span className={`tab-subtitle text-[10px] ${
              activeTab === tab.key
                ? 'text-blue-500 dark:text-blue-400'
                : 'text-gray-500 dark:text-gray-500'
            }`}>
              {tab.subtitle}
            </span>
          </button>
        ))}
      </div>

      {/* Tab Content - Scrollable */}
      <div className="flex-1 overflow-hidden min-h-0">
        <div
          className={`h-full ${activeTab === 'timeline' ? 'block' : 'hidden'}`}
          aria-hidden={activeTab !== 'timeline'}
          role="tabpanel"
        >
          {timelineContent}
        </div>
        <div
          className={`h-full ${activeTab === 'outcomes' ? 'block' : 'hidden'}`}
          aria-hidden={activeTab !== 'outcomes'}
          role="tabpanel"
        >
          {outcomesContent}
        </div>
        <div
          className={`h-full ${activeTab === 'background' ? 'block' : 'hidden'}`}
          aria-hidden={activeTab !== 'background'}
          role="tabpanel"
        >
          {backgroundContent || (
            <div className="p-4 text-sm text-gray-500 dark:text-gray-400">
              {t('backgroundTasksPanel') || 'Background Tasks Panel'}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
