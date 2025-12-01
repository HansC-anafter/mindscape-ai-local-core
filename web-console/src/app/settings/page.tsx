'use client';

import React, { useState, useEffect } from 'react';
import { useSearchParams } from 'next/navigation';
import Header from '../../components/Header';
import { t } from '../../lib/i18n';
import { TabNav } from './components/TabNav';
import { BasicSettingsPanel } from './components/BasicSettingsPanel';
import { ToolsPanel } from './components/ToolsPanel';
import { PacksPanel } from './components/PacksPanel';
import { ServiceStatusPanel } from './components/ServiceStatusPanel';
import { useTools } from './hooks/useTools';
import type { SettingsTab } from './types';

export default function SettingsPage() {
  const searchParams = useSearchParams();
  const { getToolStatusForPack } = useTools();

  // Always initialize with 'basic' to ensure server and client match
  // This prevents hydration mismatch - URL params will be read after mount
  const [activeTab, setActiveTab] = useState<SettingsTab>('basic');

  // Read URL params after hydration and update tab
  useEffect(() => {
    const tabParam = searchParams?.get('tab');
    if (tabParam === 'tools' || tabParam === 'packs' || tabParam === 'basic' || tabParam === 'service_status') {
      setActiveTab(tabParam as SettingsTab);
    }
  }, [searchParams]);

  const tabs = [
    { id: 'basic' as SettingsTab, label: t('basicSettings') },
    { id: 'tools' as SettingsTab, label: t('toolsAndIntegrations') },
    { id: 'packs' as SettingsTab, label: t('capabilityPacks') },
    { id: 'service_status' as SettingsTab, label: t('serviceStatus') || 'Service Status' },
  ];

  return (
    <div className="min-h-screen bg-gray-50">
      <Header />
      <main className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
        <div className="mb-8">
          <h1 className="text-3xl font-bold text-gray-900 mb-2">{t('systemManagement')}</h1>
          <p className="text-gray-600">{t('systemManagementDescription')}</p>
        </div>

        <div suppressHydrationWarning>
          <TabNav activeTab={activeTab} onTabChange={setActiveTab} tabs={tabs} />
        </div>

        {activeTab === 'basic' && <BasicSettingsPanel />}

        {activeTab === 'tools' && <ToolsPanel />}

        {activeTab === 'packs' && <PacksPanel getToolStatus={getToolStatusForPack} />}

        {activeTab === 'service_status' && <ServiceStatusPanel />}
      </main>
    </div>
  );
}
