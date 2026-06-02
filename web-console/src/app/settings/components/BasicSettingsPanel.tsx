'use client';

import React, { useEffect } from 'react';
import dynamic from 'next/dynamic';
import { t } from '../../../lib/i18n';
import { useBasicSettings } from '../hooks/useBasicSettings';
import { Card } from './Card';
import { showNotification } from '../hooks/useSettingsNotification';
import { BackendModeSettings } from './panels/BackendModeSettings';

interface BasicSettingsPanelProps {
  activeSection?: string;
  workspaceId?: string;
  initialCatalogCategory?: string;
}

function BasicPanelFallback() {
  return (
    <div className="rounded-lg border border-default dark:border-gray-700 bg-surface-secondary dark:bg-gray-800 p-4 text-sm text-secondary dark:text-gray-400">
      Loading...
    </div>
  );
}

const BasicSettingsSectionHost = dynamic(
  () => import('./BasicSettingsSectionHost').then((mod) => mod.BasicSettingsSectionHost),
  { ssr: false, loading: BasicPanelFallback }
);

export function BasicSettingsPanel({
  activeSection,
  workspaceId,
  initialCatalogCategory,
}: BasicSettingsPanelProps = {}) {
  const {
    loading,
    saving,
    error,
    success,
    config,
    mode,
    remoteUrl,
    remoteToken,
    openaiKey,
    anthropicKey,
    setMode,
    setRemoteUrl,
    setRemoteToken,
    setOpenaiKey,
    setAnthropicKey,
    saveSettings,
    clearError,
    clearSuccess,
  } = useBasicSettings();

  useEffect(() => {
    if (error) {
      showNotification('error', error);
      clearError();
    }
  }, [error, clearError]);

  useEffect(() => {
    if (success) {
      showNotification('success', success);
      clearSuccess();
    }
  }, [success, clearSuccess]);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    await saveSettings();
  };

  // Render specific section based on activeSection
  const renderSection = () => {
    const section = activeSection || 'backend-mode';

    switch (section) {
      case 'backend-mode':
        return (
          <div className="space-y-6">
            {loading ? (
              <div className="text-center py-4 text-sm text-secondary dark:text-gray-400">{t('loading' as any)}</div>
            ) : (
              <>
                <BackendModeSettings mode={mode} onModeChange={setMode} />
                {mode === 'remote_crs' && (
                  <div className="border-t dark:border-gray-700 pt-6 space-y-4">
                    <div>
                      <label className="block text-sm font-medium text-primary dark:text-gray-300 mb-2">
                        {t('serviceUrl' as any)} <span className="text-red-500">*</span>
                      </label>
                      <input
                        type="text"
                        value={remoteUrl}
                        onChange={(e) => setRemoteUrl(e.target.value)}
                        placeholder="https://your-agent-service.example.com"
                        className="w-full px-3 py-2 border border-default dark:border-gray-600 rounded-md focus:outline-none focus:ring-2 focus:ring-gray-500 dark:focus:ring-gray-500 bg-surface-accent dark:bg-gray-800 text-primary dark:text-gray-100"
                        required
                      />
                    </div>

                    <div>
                      <label className="block text-sm font-medium text-primary dark:text-gray-300 mb-2">
                        {t('apiToken' as any)} <span className="text-red-500">*</span>
                      </label>
                      <input
                        type="password"
                        value={remoteToken}
                        onChange={(e) => setRemoteToken(e.target.value)}
                        placeholder={
                          config?.remote_crs_configured
                            ? t('tokenPlaceholderConfigured' as any)
                            : t('tokenPlaceholder' as any)
                        }
                        className="w-full px-3 py-2 border border-default dark:border-gray-600 rounded-md focus:outline-none focus:ring-2 focus:ring-gray-500 dark:focus:ring-gray-500 bg-surface-accent dark:bg-gray-800 text-primary dark:text-gray-100"
                        required
                      />
                    </div>
                  </div>
                )}
              </>
            )}
          </div>
        );

      case 'unsplash-fingerprints':
        if (mode !== 'local') {
          return (
            <div className="text-sm text-secondary dark:text-gray-400">
              {t('unsplashFingerprints' as any) || 'Unsplash Fingerprints'} {t('availableInLocalMode' as any) || 'is only available in local mode'}
            </div>
          );
        }
        return (
          <BasicSettingsSectionHost
            activeSection={section}
            workspaceId={workspaceId}
            initialCatalogCategory={initialCatalogCategory}
          />
        );

      default:
        return (
          <BasicSettingsSectionHost
            activeSection={section}
            workspaceId={workspaceId}
            initialCatalogCategory={initialCatalogCategory}
          />
        );
    }
  };

  if (activeSection === 'runtime-backup') {
    return (
      <BasicSettingsSectionHost
        activeSection={activeSection}
        workspaceId={workspaceId}
        initialCatalogCategory={initialCatalogCategory}
      />
    );
  }

  const isStandalone = activeSection && ['models-and-quota', 'api-quota', 'embedding', 'llm-chat', 'model-routing-registry'].includes(activeSection);

  if (isStandalone) {
    return (
      <BasicSettingsSectionHost
        activeSection={activeSection}
        workspaceId={workspaceId}
        initialCatalogCategory={initialCatalogCategory}
      />
    );
  }

  const sectionContent = renderSection();

  return (
    <Card>
      <form onSubmit={handleSubmit}>
        {sectionContent}

        <div className="flex justify-end border-t dark:border-gray-700 pt-4 mt-6">
          <button
            type="submit"
            disabled={saving}
            className="px-4 py-2 bg-gray-600 dark:bg-gray-700 text-white rounded-md hover:bg-gray-700 dark:hover:bg-gray-600 disabled:opacity-50"
          >
            {saving ? t('saving' as any) : t('save' as any)}
          </button>
        </div>
      </form>
    </Card>
  );
}
