'use client';

import React from 'react';
import { useT } from '@/lib/i18n';

interface TabConfig {
  key: 'timeline' | 'outcomes' | 'pack';
  label: string;
  subtitle: string;
}

interface LeftSidebarTabsProps {
  activeTab: 'timeline' | 'outcomes' | 'pack';
  onTabChange: (tab: 'timeline' | 'outcomes' | 'pack') => void;
  timelineContent: React.ReactNode;
  outcomesContent: React.ReactNode;
  packContent?: React.ReactNode;
}

export default function LeftSidebarTabs({
  activeTab,
  onTabChange,
  timelineContent,
  outcomesContent,
  packContent
}: LeftSidebarTabsProps) {
  const t = useT();

  const tabs: TabConfig[] = [
    { key: 'timeline', label: t('tabScheduling' as any) || 'Scheduling', subtitle: t('tabSchedulingSubtitle' as any) || 'Tasks & Execution' },
    { key: 'outcomes', label: t('tabOutcomes' as any) || 'Outcomes', subtitle: t('tabOutcomesSubtitle' as any) || 'Output Overview' },
    { key: 'pack', label: t('tabPack' as any) || 'Pack', subtitle: t('tabPackSubtitle' as any) || 'Capabilities & Thinking' },
  ];

  return (
    <div className="flex flex-col h-full min-h-0">
      {/* Tab Header */}
      <div className="flex border-b dark:border-gray-700 bg-surface-secondary dark:bg-gray-800 shrink-0">
        {tabs.map((tab) => (
          <button
            key={tab.key}
            onClick={() => onTabChange(tab.key)}
            className={`group flex-1 px-4 py-2 text-xs font-medium transition-colors flex flex-col items-center ${
              activeTab === tab.key
                ? 'bg-surface-accent dark:bg-gray-900 text-accent dark:text-blue-400 border-b-2 border-accent dark:border-blue-500'
                : 'text-secondary dark:text-gray-400 hover:text-primary dark:hover:text-gray-200 hover:bg-tertiary dark:hover:bg-gray-700'
            }`}
          >
            <span className="tab-label">{tab.label}</span>
            <span className={`tab-subtitle text-[10px] transition-colors ${
              activeTab === tab.key
                ? 'text-accent dark:text-blue-400'
                : 'text-tertiary dark:text-gray-500 group-hover:text-secondary dark:group-hover:text-gray-400'
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
          className={`h-full ${activeTab === 'pack' ? 'block' : 'hidden'}`}
          aria-hidden={activeTab !== 'pack'}
          role="tabpanel"
        >
          {packContent || (
            <div className="p-4 text-sm text-gray-500 dark:text-gray-400">
              {t('packPanel' as any) || 'Pack Panel'}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
