'use client';

import React, { useState, useEffect, useRef, useCallback } from 'react';
import dynamic from 'next/dynamic';
import { useSearchParams, useRouter } from 'next/navigation';
import Header from '../../components/Header';
import { t } from '../../lib/i18n';
import { SettingsNavigation } from './components/SettingsNavigation';
import { SettingsConfigAssistant, type SettingsConfigAssistantHandle } from './components/SettingsConfigAssistant';
import { SettingsNotificationContainer } from './hooks/useSettingsNotification';
import type { SettingsTab } from './types';

function SettingsPanelFallback() {
  return (
    <div
      role="status"
      aria-live="polite"
      className="rounded-lg border border-default dark:border-gray-700 bg-surface-secondary dark:bg-gray-800 p-4 text-sm text-secondary dark:text-gray-400"
    >
      Loading...
    </div>
  );
}

const SettingsContentHost = dynamic(
  () => import('./components/SettingsContentHost').then((mod) => mod.SettingsContentHost),
  { ssr: false, loading: SettingsPanelFallback }
);

const VALID_SETTINGS_TABS: SettingsTab[] = [
  'tools',
  'basic',
  'credentials',
  'mindscape',
  'ai-team-governance',
  'social_media',
  'localization',
  'service_status',
  'packs_status',
  'governance',
  'runtime',
  'remote_workbench_access',
];

interface SearchParamsReader {
  get(name: string): string | null;
}

interface SettingsRouteState {
  activeTab: SettingsTab;
  activeSection?: string;
  activeProvider?: string;
  activeModel?: string;
  activeService?: string;
  workspaceId?: string;
  initialCatalogCategory?: string;
}

function resolveSettingsRoute(searchParams: SearchParamsReader | null): SettingsRouteState {
  const tabParam = searchParams?.get('tab');
  const sectionParam = searchParams?.get('section');
  const credentialsSections = new Set(['service-credentials', 'oauth-integrations', 'oauth']);
  let activeTab = tabParam && VALID_SETTINGS_TABS.includes(tabParam as SettingsTab)
    ? tabParam as SettingsTab
    : 'basic';

  if (activeTab === 'basic' && sectionParam && credentialsSections.has(sectionParam)) {
    activeTab = 'credentials';
  }
  if (activeTab === 'credentials' && sectionParam === 'models-and-quota') {
    activeTab = 'basic';
  }

  let activeSection: string | undefined;
  if (sectionParam) {
    activeSection = sectionParam === 'oauth' ? 'oauth-integrations' : sectionParam;
  } else if (activeTab === 'basic') {
    activeSection = 'backend-mode';
  } else if (activeTab === 'credentials') {
    activeSection = 'service-credentials';
  } else if (activeTab === 'packs_status') {
    activeSection = 'packages';
  }

  return {
    activeTab,
    activeSection,
    activeProvider: searchParams?.get('provider') || undefined,
    activeModel: searchParams?.get('model') || undefined,
    activeService: searchParams?.get('service') || undefined,
    workspaceId: searchParams?.get('workspace_id') || undefined,
    initialCatalogCategory: searchParams?.get('catalog') || undefined,
  };
}

export default function SettingsPage() {
  const searchParams = useSearchParams();
  const router = useRouter();
  const initialRoute = resolveSettingsRoute(searchParams);

  const [activeTab, setActiveTab] = useState<SettingsTab>(initialRoute.activeTab);
  const [activeSection, setActiveSection] = useState<string | undefined>(initialRoute.activeSection);
  const [activeProvider, setActiveProvider] = useState<string | undefined>(initialRoute.activeProvider);
  const [activeModel, setActiveModel] = useState<string | undefined>(initialRoute.activeModel);
  const [activeService, setActiveService] = useState<string | undefined>(initialRoute.activeService);
  const [workspaceId, setWorkspaceId] = useState<string | undefined>(initialRoute.workspaceId);
  const [initialCatalogCategory, setInitialCatalogCategory] = useState<string | undefined>(initialRoute.initialCatalogCategory);

  // Ref for Chat-First UX - allows buttons to trigger assistant chat
  const assistantRef = useRef<SettingsConfigAssistantHandle>(null);
  const handleSendToAssistant = useCallback((message: string) => {
    assistantRef.current?.sendMessage(message);
  }, []);

  useEffect(() => {
    const route = resolveSettingsRoute(searchParams);
    setActiveTab(route.activeTab);
    setActiveSection(route.activeSection);
    setActiveProvider(route.activeProvider);
    setActiveModel(route.activeModel);
    setActiveService(route.activeService);
    setWorkspaceId(route.workspaceId);
    setInitialCatalogCategory(route.initialCatalogCategory);
  }, [searchParams]);

  const handleNavigate = (tab: SettingsTab, section?: string, provider?: string, model?: string, service?: string) => {
    const normalizedSection = tab === 'credentials' && !section
      ? 'service-credentials'
      : section;
    setActiveTab(tab);
    setActiveSection(normalizedSection);
    setActiveProvider(provider);
    setActiveModel(model);
    setActiveService(service);

    const params = new URLSearchParams();
    params?.set('tab', tab);
    if (normalizedSection) {
      params?.set('section', normalizedSection);
    }
    if (provider) {
      params?.set('provider', provider);
    }
    if (model) {
      params?.set('model', model);
    }
    if (service) {
      params?.set('service', service);
    }
    if (workspaceId) {
      params?.set('workspace_id', workspaceId);
    }
    if (initialCatalogCategory && tab === 'basic') {
      params?.set('catalog', initialCatalogCategory);
    }
    router.push(`/settings?${params?.toString()}`);
  };

  const content = (
    <SettingsContentHost
      activeTab={activeTab}
      activeSection={activeSection}
      activeProvider={activeProvider}
      workspaceId={workspaceId}
      initialCatalogCategory={initialCatalogCategory}
      onCredentialsNavigate={(section, provider) => handleNavigate('credentials', section, provider)}
      onSendToAssistant={handleSendToAssistant}
    />
  );

  return (
    <div className="h-screen flex flex-col overflow-hidden bg-surface dark:bg-gray-900">
      <Header />

      {/* Page Header */}
      <div className="bg-surface-secondary dark:bg-gray-800 border-b border-default dark:border-gray-700 z-40 shrink-0">
        <div className="w-full px-4 sm:px-6 lg:px-12 py-3 flex items-center gap-4">
          <h1 className="text-xl font-bold text-primary dark:text-gray-100 flex-shrink-0 min-w-0">
            {t('systemManagement' as any)} <span className="text-sm font-normal text-secondary dark:text-gray-400 ml-2">{t('systemManagementDescription' as any)}</span>
          </h1>
          <div id="settings-notifications" className="flex items-center gap-2 min-w-0 flex-shrink max-w-xs ml-auto"></div>
        </div>
        <SettingsNotificationContainer />
      </div>

      {/* Mobile Navigation (only on small screens) */}
      <div className="lg:hidden bg-surface-secondary dark:bg-gray-800 border-b border-default dark:border-gray-700 px-4 py-2 shrink-0">
        <div className="flex gap-2 overflow-x-auto">
          {[
            { id: 'basic' as SettingsTab, label: t('basicSettings' as any) },
            { id: 'credentials' as SettingsTab, label: t('credentialsAndOAuth' as any) },
            { id: 'mindscape' as SettingsTab, label: t('mindscapeConfiguration' as any) },
            { id: 'social_media' as SettingsTab, label: t('socialMediaIntegration' as any) },
            { id: 'localization' as SettingsTab, label: t('localization' as any) },
            { id: 'packs_status' as SettingsTab, label: t('capabilityPacks' as any) },
            { id: 'governance' as SettingsTab, label: t('governance' as any) },
            { id: 'runtime' as SettingsTab, label: t('runtimeEnvironments' as any) },
            { id: 'remote_workbench_access' as SettingsTab, label: t('remoteWorkbenchAccess' as any) },
            { id: 'service_status' as SettingsTab, label: t('serviceStatus' as any) },
          ].map((tab) => (
            <button
              key={tab.id}
              type="button"
              onClick={() => handleNavigate(tab.id)}
              aria-current={activeTab === tab.id ? 'page' : undefined}
              className={`px-3 py-1.5 text-sm font-medium whitespace-nowrap rounded-md ${activeTab === tab.id
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
      <main className="w-full flex-1 flex flex-col min-h-0">
        <div className="grid grid-cols-12 flex-1 min-h-0">
          {/* Left Column: Navigation (Desktop only) - col-span-2 (16.67%) */}
          <div className="hidden lg:block col-span-2 h-full min-h-0">
            <div className="bg-surface-secondary dark:bg-gray-800 h-full overflow-y-auto flex flex-col z-30 border-r border-default dark:border-gray-700">
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
          <div className={`col-span-12 ${activeTab === 'remote_workbench_access' ? 'lg:col-span-10' : 'lg:col-span-7'} flex flex-col h-full min-h-0 bg-surface dark:bg-gray-900`}>
            {(activeTab === 'basic' && activeSection === 'models-and-quota') ? (
              <div className="flex-1 flex flex-col min-h-0 p-3 lg:p-4">
                {content}
              </div>
            ) : (
              <div className="flex-1 overflow-y-auto min-h-0 p-3 lg:p-4">
                {content}
              </div>
            )}
          </div>

          {/* Right Column: Assistant (Desktop only) - col-span-3 (25%) */}
          {activeTab !== 'remote_workbench_access' ? (
            <div className="hidden lg:block col-span-3 h-full min-h-0" data-testid="settings-config-assistant-column">
              <div className="bg-surface-secondary dark:bg-gray-800 h-full overflow-y-auto flex flex-col p-4 z-30 border-l border-default dark:border-gray-700">
                <h3 className="text-sm font-semibold text-primary dark:text-gray-100 mb-3">
                  {t('configAssistant' as any)}
                </h3>
                <div className="flex-1 min-h-0 overflow-hidden">
                  <SettingsConfigAssistant
                    ref={assistantRef}
                    currentTab={activeTab}
                    currentSection={activeSection}
                    onNavigate={(tab, section) => handleNavigate(tab, section)}
                  />
                </div>
              </div>
            </div>
          ) : null}
        </div>
      </main>
    </div>
  );
}
