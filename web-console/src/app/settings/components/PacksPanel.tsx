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
import type { ToolStatus } from '../types';

interface PacksPanelProps {
  getToolStatus: (toolType: string) => ToolStatus;
}

type PackTab = 'suites' | 'packages';

export function PacksPanel({ getToolStatus }: PacksPanelProps) {
  const { packs, installingPack, loadPacks, installPack } = usePacks();
  const [activeTab, setActiveTab] = useState<PackTab>('suites');
  const [installSuccess, setInstallSuccess] = useState<string | null>(null);
  const [installError, setInstallError] = useState<string | null>(null);
  const [refreshTrigger, setRefreshTrigger] = useState(0);

  React.useEffect(() => {
    loadPacks();
  }, [loadPacks]);

  const handleInstall = async (packId: string) => {
    setInstallError(null);
    setInstallSuccess(null);
    try {
      await installPack(packId);
      setInstallSuccess(t('packInstalledSuccessfully'));
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
      </div>

      {/* Tab Content */}
      {activeTab === 'suites' && (
        <Section
          title={t('capabilitySuites')}
          description={t('capabilitySuitesDescription')}
        >
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
            {packs.map((pack) => (
              <PackCard
                key={pack.id}
                pack={pack}
                onInstall={() => handleInstall(pack.id)}
                installing={installingPack === pack.id}
                getToolStatus={getToolStatus}
              />
            ))}
          </div>
        </Section>
      )}

      {activeTab === 'packages' && (
        <Section
          title={t('capabilityPackages')}
          description={t('capabilityPackagesDescription')}
        >
          <div className="mb-8">
            <Card className="p-4 bg-gray-50">
              <h3 className="text-lg font-semibold text-gray-900 mb-2">{t('installFromFile')}</h3>
              <p className="text-sm text-gray-600 mb-4">{t('installFromFileDescription')}</p>
              <InstallFromFileButton onSuccess={() => {
                loadPacks();
                // Trigger refresh of installed capabilities list
                setRefreshTrigger(prev => prev + 1);
              }} />
            </Card>
          </div>

          <InstalledCapabilitiesList refreshTrigger={refreshTrigger} />
        </Section>
      )}
    </div>
  );
}
