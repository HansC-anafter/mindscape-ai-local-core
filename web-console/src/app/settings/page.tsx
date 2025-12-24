'use client';

import React, { useState, useEffect } from 'react';
import { useSearchParams, useRouter } from 'next/navigation';
import Header from '../../components/Header';
import { t } from '../../lib/i18n';
import { SettingsNavigation } from './components/SettingsNavigation';
import { SettingsConfigAssistant } from './components/SettingsConfigAssistant';
import { BasicSettingsPanel } from './components/BasicSettingsPanel';
import { MindscapePanel } from './components/MindscapePanel';
import { SettingsNotificationContainer } from './hooks/useSettingsNotification';
import { SocialMediaPanel } from './components/SocialMediaPanel';
import { ToolsPanel } from './components/ToolsPanel';
import { PacksPanel } from './components/PacksPanel';
import { LocalizationPanel } from './components/LocalizationPanel';
import { ServiceStatusPanel } from './components/ServiceStatusPanel';
import { GovernancePanel } from './components/GovernancePanel';
import { useTools } from './hooks/useTools';
import type { SettingsTab } from './types';

export default function SettingsPage() {
  const searchParams = useSearchParams();
  const router = useRouter();
  const { getToolStatusForPack } = useTools();

  const [activeTab, setActiveTab] = useState<SettingsTab>('basic');
  const [activeSection, setActiveSection] = useState<string | undefined>();
  const [activeProvider, setActiveProvider] = useState<string | undefined>();
  const [activeModel, setActiveModel] = useState<string | undefined>();
  const [activeService, setActiveService] = useState<string | undefined>();

  useEffect(() => {
    const tabParam = searchParams?.get('tab');
    const sectionParam = searchParams?.get('section');
    const providerParam = searchParams?.get('provider');
    const modelParam = searchParams?.get('model');
    const serviceParam = searchParams?.get('service');

    const validTabs: SettingsTab[] = ['tools', 'packs', 'basic', 'mindscape', 'social_media', 'localization', 'service_status', 'governance'];
    if (tabParam && validTabs.includes(tabParam as SettingsTab)) {
      setActiveTab(tabParam as SettingsTab);
    }

    if (sectionParam) {
      setActiveSection(sectionParam);
    } else if (tabParam === 'basic' && !sectionParam) {
      setActiveSection('backend-mode');
    }

    if (providerParam) {
      setActiveProvider(providerParam);
    }

    if (modelParam) {
      setActiveModel(modelParam);
    }

    if (serviceParam) {
      setActiveService(serviceParam);
    }
  }, [searchParams]);

  const handleNavigate = (tab: SettingsTab, section?: string, provider?: string, model?: string, service?: string) => {
    setActiveTab(tab);
    setActiveSection(section);
    setActiveProvider(provider);
    setActiveModel(model);
    setActiveService(service);

    const params = new URLSearchParams();
    params.set('tab', tab);
    if (section) {
      params.set('section', section);
    }
    if (provider) {
      params.set('provider', provider);
    }
    if (model) {
      params.set('model', model);
    }
    if (service) {
      params.set('service', service);
    }
    router.push(`/settings?${params.toString()}`);
  };

  const renderContent = () => {
    switch (activeTab) {
      case 'basic':
        return <BasicSettingsPanel activeSection={activeSection} />;
      case 'mindscape':
        return <MindscapePanel />;
      case 'social_media':
        return <SocialMediaPanel activeProvider={activeProvider} />;
      case 'tools':
        return <ToolsPanel activeSection={activeSection} activeProvider={activeProvider} />;
      case 'packs':
        return <PacksPanel getToolStatus={getToolStatusForPack} activeSection={activeSection} />;
      case 'localization':
        return <LocalizationPanel activeSection={activeSection} />;
      case 'service_status':
        return <ServiceStatusPanel />;
      case 'governance':
        return <GovernancePanel activeSection={activeSection} />;
      default:
        return <BasicSettingsPanel activeSection={activeSection} />;
    }
  };

  return (
    <div className="min-h-screen bg-surface dark:bg-gray-900">
      <Header />

      {/* Page Header */}
      <div className="bg-surface-secondary dark:bg-gray-800 border-b border-default dark:border-gray-700 sticky top-12 z-40">
        <div className="w-full px-4 sm:px-6 lg:px-12 py-3 flex items-center gap-4">
          <h1 className="text-xl font-bold text-primary dark:text-gray-100 flex-shrink-0 min-w-0">
            {t('systemManagement')} <span className="text-sm font-normal text-secondary dark:text-gray-400 ml-2">{t('systemManagementDescription')}</span>
          </h1>
          <div id="settings-notifications" className="flex items-center gap-2 min-w-0 flex-shrink max-w-xs ml-auto"></div>
        </div>
        <SettingsNotificationContainer />
      </div>

      {/* Mobile Navigation (only on small screens) */}
      <div className="lg:hidden bg-surface-secondary dark:bg-gray-800 border-b border-default dark:border-gray-700 px-4 py-2">
        <div className="flex gap-2 overflow-x-auto">
          {[
            { id: 'basic' as SettingsTab, label: t('basicSettings') },
            { id: 'mindscape' as SettingsTab, label: t('mindscapeConfiguration') },
            { id: 'social_media' as SettingsTab, label: t('socialMediaIntegration') },
            { id: 'localization' as SettingsTab, label: t('localization') },
            { id: 'governance' as SettingsTab, label: t('governance') },
            { id: 'service_status' as SettingsTab, label: t('serviceStatus') },
          ].map((tab) => (
            <button
              key={tab.id}
              onClick={() => handleNavigate(tab.id)}
              className={`px-3 py-1.5 text-sm font-medium whitespace-nowrap rounded-md ${
                activeTab === tab.id
                  ? 'bg-surface-secondary dark:bg-gray-800 text-primary dark:text-gray-300'
                  : 'text-secondary dark:text-gray-400 hover:bg-surface-secondary dark:hover:bg-gray-700'
              }`}
            >
              {tab.label}
            </button>
          ))}
        </div>
      </div>

      {/* Three Column Layout */}
      <main className="w-full">
        <div className="grid grid-cols-12">
          {/* Left Column: Navigation (Desktop only) - col-span-2 (16.67%) */}
          <div className="hidden lg:block col-span-2">
            <div className="bg-surface-secondary dark:bg-gray-800 h-[calc(100vh-8rem)] flex flex-col sticky top-[calc(3rem+3rem)] z-30 border-r border-default dark:border-gray-700">
              <SettingsNavigation
                activeTab={activeTab}
                activeSection={activeSection}
                activeProvider={activeProvider}
                activeModel={activeModel}
                activeService={activeService}
                onNavigate={handleNavigate}
              />
            </div>
          </div>

          {/* Middle Column: Content - col-span-7 (58.33%) */}
          <div className="col-span-12 lg:col-span-7 flex flex-col">
            <div className="flex-1 overflow-y-auto min-h-[calc(100vh-8rem)] p-4">
              {renderContent()}
            </div>
          </div>

          {/* Right Column: Assistant (Desktop only) - col-span-3 (25%) */}
          <div className="hidden lg:block col-span-3">
            <div className="bg-surface-secondary dark:bg-gray-800 h-[calc(100vh-8rem)] flex flex-col p-4 sticky top-[calc(3rem+3rem)] z-30 border-l border-default dark:border-gray-700">
              <h3 className="text-sm font-semibold text-primary dark:text-gray-100 mb-3">
                {t('configAssistant')}
              </h3>
              <div className="flex-1 min-h-0 overflow-hidden">
                <SettingsConfigAssistant
                  currentTab={activeTab}
                  currentSection={activeSection}
                  onNavigate={(tab, section) => handleNavigate(tab, section)}
                />
              </div>
            </div>
          </div>
        </div>
      </main>
    </div>
  );
}
