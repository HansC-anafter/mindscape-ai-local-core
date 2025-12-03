'use client';

import React, { useState, useEffect } from 'react';
import { useSearchParams, useRouter } from 'next/navigation';
import Header from '../../components/Header';
import { t } from '../../lib/i18n';
import { SettingsNavigation } from './components/SettingsNavigation';
import { SettingsConfigAssistant } from './components/SettingsConfigAssistant';
import { BasicSettingsPanel } from './components/BasicSettingsPanel';
import { ToolsPanel } from './components/ToolsPanel';
import { PacksPanel } from './components/PacksPanel';
import { ServiceStatusPanel } from './components/ServiceStatusPanel';
import { useTools } from './hooks/useTools';
import type { SettingsTab } from './types';

export default function SettingsPage() {
  const searchParams = useSearchParams();
  const router = useRouter();
  const { getToolStatusForPack } = useTools();

  const [activeTab, setActiveTab] = useState<SettingsTab>('basic');
  const [activeSection, setActiveSection] = useState<string | undefined>();

  useEffect(() => {
    const tabParam = searchParams?.get('tab');
    const sectionParam = searchParams?.get('section');

    if (tabParam === 'tools' || tabParam === 'packs' || tabParam === 'basic' || tabParam === 'service_status') {
      setActiveTab(tabParam as SettingsTab);
    }

    if (sectionParam) {
      setActiveSection(sectionParam);
    }
  }, [searchParams]);

  const handleNavigate = (tab: SettingsTab, section?: string) => {
    setActiveTab(tab);
    setActiveSection(section);

    const params = new URLSearchParams();
    params.set('tab', tab);
    if (section) {
      params.set('section', section);
    }
    router.push(`/settings?${params.toString()}`);
  };

  const renderContent = () => {
    switch (activeTab) {
      case 'basic':
        return <BasicSettingsPanel />;
      case 'tools':
        return <ToolsPanel />;
      case 'packs':
        return <PacksPanel getToolStatus={getToolStatusForPack} />;
      case 'service_status':
        return <ServiceStatusPanel />;
      default:
        return <BasicSettingsPanel />;
    }
  };

  return (
    <div className="min-h-screen bg-gray-50">
      <Header />

      {/* Page Header */}
      <div className="bg-white border-b border-gray-200">
        <div className="w-full px-4 sm:px-6 lg:px-12 py-3">
          <h1 className="text-xl font-bold text-gray-900">
            {t('systemManagement')} <span className="text-sm font-normal text-gray-600 ml-2">{t('systemManagementDescription')}</span>
          </h1>
        </div>
      </div>

      {/* Mobile Navigation (only on small screens) */}
      <div className="lg:hidden bg-white border-b border-gray-200 px-4 py-2">
        <div className="flex gap-2 overflow-x-auto">
          {[
            { id: 'basic' as SettingsTab, label: t('basicSettings') },
            { id: 'tools' as SettingsTab, label: t('toolsAndIntegrations') },
            { id: 'packs' as SettingsTab, label: t('capabilityPacks') },
            { id: 'service_status' as SettingsTab, label: t('serviceStatus') },
          ].map((tab) => (
            <button
              key={tab.id}
              onClick={() => handleNavigate(tab.id)}
              className={`px-3 py-1.5 text-sm font-medium whitespace-nowrap rounded-md ${
                activeTab === tab.id
                  ? 'bg-purple-100 text-purple-700'
                  : 'text-gray-600 hover:bg-gray-100'
              }`}
            >
              {tab.label}
            </button>
          ))}
        </div>
      </div>

      {/* Three Column Layout */}
      <main className="w-full">
        <div className="grid grid-cols-12 gap-0">
          {/* Left Column: Navigation (Desktop only) - Narrower */}
          <div className="hidden lg:block col-span-1">
            <SettingsNavigation
              activeTab={activeTab}
              activeSection={activeSection}
              onNavigate={handleNavigate}
            />
          </div>

          {/* Middle Column: Content - More space */}
          <div className="col-span-12 lg:col-span-8">
            <div className="min-h-[calc(100vh-8rem)] lg:h-[calc(100vh-8rem)] overflow-y-auto p-4">
              {renderContent()}
            </div>
          </div>

          {/* Right Column: Assistant (Desktop only) */}
          <div className="hidden lg:block col-span-3">
            <div className="bg-white shadow h-[calc(100vh-8rem)] flex flex-col p-4 sticky top-0">
              <h3 className="text-sm font-semibold text-gray-900 mb-3">
                {t('configAssistant')}
              </h3>
              <div className="flex-1 min-h-0 overflow-hidden">
                <SettingsConfigAssistant
                  currentTab={activeTab}
                  currentSection={activeSection}
                  onNavigate={handleNavigate}
                />
              </div>
            </div>
          </div>
        </div>
      </main>
    </div>
  );
}
