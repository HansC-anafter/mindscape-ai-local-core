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
  activeSection?: string;
}

export function PacksPanel({ getToolStatus, activeSection }: PacksPanelProps) {
  const { packs, loading: packsLoading, installingPack, loadPacks, installPack } = usePacks();
  const { suites, loading: suitesLoading, installingSuite, loadSuites, installSuite } = useSuites();
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
      setInstallSuccess(t('packInstalledSuccessfully' as any));
      loadPacks();
      loadSuites();
    } catch (err) {
      setInstallError(
        `${t('installationFailed' as any)}: ${err instanceof Error ? err.message : 'Unknown error'}`
      );
    }
  };

  const handleInstallSuite = async (suiteId: string) => {
    setInstallError(null);
    setInstallSuccess(null);
    try {
      await installSuite(suiteId);
      setInstallSuccess(t('packInstalledSuccessfully' as any));
      loadSuites();
      loadPacks();
    } catch (err) {
      setInstallError(
        `${t('installationFailed' as any)}: ${err instanceof Error ? err.message : 'Unknown error'}`
      );
    }
  };

  // Show empty state if no section is selected
  if (!activeSection) {
    return (
      <div className="text-center py-12 text-gray-500 dark:text-gray-400">
        <p>{t('capabilityPacks' as any)}</p>
        <p className="text-sm mt-2">{t('selectPacksSection' as any) || '請選擇能力套裝或能力包'}</p>
      </div>
    );
  }

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

      {/* Section Content */}
      {activeSection === 'suites' && (
        <Section
          description={t('capabilitySuitesDescription' as any)}
        >
          {suitesLoading ? (
            <div className="text-center py-12">
              <p className="text-gray-500 dark:text-gray-400 text-sm">載入中...</p>
            </div>
          ) : suites.length === 0 ? (
            <div className="text-center py-12">
              <p className="text-gray-500 dark:text-gray-400 text-sm">無可用能力套裝</p>
              <p className="text-gray-400 dark:text-gray-500 text-xs mt-2">能力套裝從共享層載入</p>
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

      {activeSection === 'packages' && (
        <Section
          description={t('capabilityPackagesDescription' as any)}
        >
          {packsLoading ? (
            <div className="text-center py-12">
              <p className="text-gray-500 dark:text-gray-400 text-sm">載入中...</p>
            </div>
          ) : (
            <>
              <div className="flex items-center justify-end mb-4">
                <div className="relative">
                  <div className="flex items-center gap-2">
                    <div className="relative">
                      <button
                        type="button"
                        className="text-gray-400 dark:text-gray-500 hover:text-gray-600 dark:hover:text-gray-300 transition-colors"
                        onClick={() => setShowTooltip(!showTooltip)}
                        onBlur={() => setTimeout(() => setShowTooltip(false), 200)}
                      >
                        <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8.228 9c.549-1.165 2.03-2 3.772-2 2.21 0 4 1.343 4 3 0 1.4-1.278 2.575-3.006 2.907-.542.104-.994.54-.994 1.093m0 3h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
                        </svg>
                      </button>
                      {showTooltip && (
                        <div className="absolute right-0 top-full mt-2 w-64 p-3 bg-gray-900 text-white text-xs rounded-lg shadow-lg z-50">
                          <p className="whitespace-normal">{t('installFromFileDescription' as any)}</p>
                          <div className="absolute -top-1 right-4 w-2 h-2 bg-gray-900 transform rotate-45"></div>
                        </div>
                      )}
                    </div>
                    <InstallFromFileButton onSuccess={() => {
                      loadPacks();
                      loadSuites();
                      setRefreshTrigger(prev => prev + 1);
                    }} />
                  </div>
                </div>
              </div>
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
            </>
          )}
        </Section>
      )}
    </div>
  );
}
