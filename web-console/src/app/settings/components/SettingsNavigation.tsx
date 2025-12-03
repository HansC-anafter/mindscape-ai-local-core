'use client';

import React from 'react';
import { t } from '../../../lib/i18n';
import type { SettingsTab } from '../types';

interface NavigationItem {
  id: string;
  label: string;
  icon?: string;
  tab: SettingsTab;
  section?: string;
}

interface SettingsNavigationProps {
  activeTab: SettingsTab;
  activeSection?: string;
  onNavigate: (tab: SettingsTab, section?: string) => void;
}

const navigationItems: NavigationItem[] = [
  {
    id: 'basic',
    label: 'basicSettings',
    icon: '📋',
    tab: 'basic',
  },
  {
    id: 'tools',
    label: 'toolsAndIntegrations',
    icon: '🔧',
    tab: 'tools',
  },
  {
    id: 'packs',
    label: 'capabilityPacks',
    icon: '📦',
    tab: 'packs',
  },
  {
    id: 'service_status',
    label: 'serviceStatus',
    icon: '📊',
    tab: 'service_status',
  },
];

export function SettingsNavigation({
  activeTab,
  activeSection,
  onNavigate,
}: SettingsNavigationProps) {
  return (
    <div className="bg-white shadow h-[calc(100vh-8rem)] overflow-y-auto p-1 sticky top-0">
      <h3 className="text-xs font-semibold text-gray-900 mb-1.5 px-1">
        {t('systemManagement')}
      </h3>

      <nav className="space-y-0.5">
        {navigationItems.map((item) => {
          const isActive = activeTab === item.tab;
          return (
            <button
              key={item.id}
              onClick={() => onNavigate(item.tab)}
              className={`w-full text-left px-1 py-0.5 rounded-md text-xs font-medium transition-colors ${
                isActive
                  ? 'bg-purple-50 text-purple-700 border-l-4 border-purple-500'
                  : 'text-gray-700 hover:bg-gray-50'
              }`}
            >
              <div className="flex items-center gap-1">
                {item.icon && <span className="text-xs">{item.icon}</span>}
                <span>{t(item.label as any)}</span>
              </div>
            </button>
          );
        })}
      </nav>
    </div>
  );
}

