'use client';

import React, { useState } from 'react';
import { t } from '../../../lib/i18n';
import { Section } from './Section';
import { PackCard } from './PackCard';
import { InstallFromFileButton } from './InstallFromFileButton';
import { InstalledCapabilitiesList } from './InstalledCapabilitiesList';
import { Card } from './Card';
import { InlineAlert } from './InlineAlert';
import { usePacks } from '../hooks/usePacks';
import { useSuites } from '../hooks/useSuites';
import type { ToolStatus } from '../types';

interface PacksPanelProps {
  getToolStatus: (toolType: string) => ToolStatus;
}

type PackTab = 'suites' | 'packages';

export function PacksPanel({ getToolStatus }: PacksPanelProps) {
  const { packs, installingPack, loadPacks, installPack } = usePacks();
  const { suites, installingSuite, loadSuites, installSuite } = useSuites();
  const [activeTab, setActiveTab] = useState<PackTab>('suites');
  const [installSuccess, setInstallSuccess] = useState<string | null>(null);
  const [installError, setInstallError] = useState<string | null>(null);
  const [refreshTrigger, setRefreshTrigger] = useState(0);
  const [showTooltip, setShowTooltip] = useState(false);

  React.useEffect(() => {
    loadPacks();
    loadSuites();
  }, [loadPacks, loadSuites]);

  const handleInstallPack = async (packId: string) => {
    setInstallError(null);
    setInstallSuccess(null);
    try {
      await installPack(packId);
      setInstallSuccess(t('packInstalledSuccessfully'));
      loadPacks();
      loadSuites();
    } catch (err) {
      setInstallError(
        `${t('installationFailed')}: ${err instanceof Error ? err.message : 'Unknown error'}`
      );
    }
  };

  const handleInstallSuite = async (suiteId: string) => {
    setInstallError(null);
    setInstallSuccess(null);
    try {
      await installSuite(suiteId);
      setInstallSuccess(t('packInstalledSuccessfully'));
      loadSuites();
      loadPacks();
    } catch (err) {
      setInstallError(
        `${t('installationFailed')}: ${err instanceof Error ? err.message : 'Unknown error'}`
      );
    }
  };

  const tabs = [
    { id: 'suites' as PackTab, label: t('capabilitySuites') },
    { id: 'packages' as PackTab, label: t('capabilityPackages') },
  ];

  return (
    <div className="space-y-6">
      {installSuccess && (
        <InlineAlert
          type="success"
          message={installSuccess}
          onDismiss={() => setInstallSuccess(null)}
        />
      )}

      {installError && (
        <InlineAlert
          type="error"
          message={installError}
          onDismiss={() => setInstallError(null)}
        />
      )}

      {/* Tab Navigation */}
      <div className="border-b border-gray-200">
        <div className="flex items-center justify-between">
          <nav className="-mb-px flex space-x-8" aria-label="Tabs">
            {tabs.map((tab) => (
              <button
                key={tab.id}
                onClick={() => setActiveTab(tab.id)}
                className={`
                  whitespace-nowrap py-4 px-1 border-b-2 font-medium text-sm
                  ${
                    activeTab === tab.id
                      ? 'border-purple-500 text-purple-600'
                      : 'border-transparent text-gray-500 hover:text-gray-700 hover:border-gray-300'
                  }
                `}
              >
                {tab.label}
              </button>
            ))}
          </nav>

          {/* Install from File - show on both tabs */}
          <div className="flex items-center gap-2">
            <div className="relative">
              <button
                type="button"
                className="text-gray-400 hover:text-gray-600 transition-colors"
                onClick={() => setShowTooltip(!showTooltip)}
                onBlur={() => setTimeout(() => setShowTooltip(false), 200)}
              >
                <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8.228 9c.549-1.165 2.03-2 3.772-2 2.21 0 4 1.343 4 3 0 1.4-1.278 2.575-3.006 2.907-.542.104-.994.54-.994 1.093m0 3h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
                </svg>
              </button>
              {showTooltip && (
                <div className="absolute right-0 top-full mt-2 w-64 p-3 bg-gray-900 text-white text-xs rounded-lg shadow-lg z-50">
                  <p className="whitespace-normal">{t('installFromFileDescription')}</p>
                  <div className="absolute -top-1 right-4 w-2 h-2 bg-gray-900 transform rotate-45"></div>
                </div>
              )}
            </div>
            <InstallFromFileButton onSuccess={() => {
              loadPacks();
              loadSuites();
              // Trigger refresh of installed capabilities list
              setRefreshTrigger(prev => prev + 1);
            }} />
          </div>
        </div>
      </div>

      {/* Tab Content */}
      {activeTab === 'suites' && (
        <Section
          description={t('capabilitySuitesDescription')}
        >
          {suites.length === 0 ? (
            <div className="text-center py-12">
              <p className="text-gray-500 text-sm">{t('noCapabilitySuitesAvailable') || 'No capability suites available'}</p>
              <p className="text-gray-400 text-xs mt-2">{t('capabilitySuitesFromSharedLayer') || 'Capability suites are loaded from the shared layer'}</p>
            </div>
          ) : (
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
              {suites.map((suite) => (
                <PackCard
                  key={suite.id}
                  pack={{
                    id: suite.id,
                    name: suite.name,
                    description: suite.description,
                    icon: suite.icon,
                    ai_members: suite.ai_members,
                    capabilities: suite.capabilities,
                    playbooks: suite.playbooks,
                    required_tools: suite.required_tools,
                    installed: suite.installed,
                  }}
                  onInstall={() => handleInstallSuite(suite.id)}
                  installing={installingSuite === suite.id}
                  getToolStatus={getToolStatus}
                />
              ))}
            </div>
          )}
        </Section>
      )}

      {activeTab === 'packages' && (
        <Section
          description={t('capabilityPackagesDescription')}
        >
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6 mb-8">
            {packs.map((pack) => (
              <PackCard
                key={pack.id}
                pack={pack}
                onInstall={() => handleInstallPack(pack.id)}
                installing={installingPack === pack.id}
                getToolStatus={getToolStatus}
              />
            ))}
          </div>

          <InstalledCapabilitiesList refreshTrigger={refreshTrigger} />
        </Section>
      )}
    </div>
  );
}
