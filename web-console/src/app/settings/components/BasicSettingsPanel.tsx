'use client';

import React, { useEffect } from 'react';
import { t } from '../../../lib/i18n';
import { useBasicSettings } from '../hooks/useBasicSettings';
import { Card } from './Card';
import { showNotification } from '../hooks/useSettingsNotification';
import { LLMModelSettings } from './LLMModelSettings';
import { GoogleOAuthSettings } from './GoogleOAuthSettings';
import { BackendModeSettings } from './panels/BackendModeSettings';
import { ModelsAndQuotaPanel } from './panels/ModelsAndQuotaPanel';
import { APIAndQuotaSettings } from './panels/APIAndQuotaSettings';
import { EmbeddingSettings } from './panels/EmbeddingSettings';
import { LLMChatSettings } from './panels/LLMChatSettings';
import { BackendStatusSection } from './panels/BackendStatusSection';
import { LanguagePreferencesSettings } from './panels/LanguagePreferencesSettings';
import { ThemePresetSettings } from './panels/ThemePresetSettings';
import { CloudExtensionSettings } from './panels/CloudExtensionSettings';
import { UnsplashFingerprintsSettings } from './panels/UnsplashFingerprintsSettings';
import { PortConfigurationSettings } from './panels/PortConfigurationSettings';

interface BasicSettingsPanelProps {
  activeSection?: string;
}

export function BasicSettingsPanel({ activeSection }: BasicSettingsPanelProps = {}) {
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
    if (!activeSection) {
      return null;
    }

    switch (activeSection) {
      case 'models-and-quota':
        return <ModelsAndQuotaPanel />;
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

      case 'api-quota':
        if (loading) {
          return (
            <div className="text-center py-4 text-sm text-secondary">{t('loading' as any)}</div>
          );
        }
        if (mode !== 'local') {
          return (
            <div className="text-sm text-secondary dark:text-gray-400">
              {t('apiAndQuota' as any) || 'API 與配額'} {t('availableInLocalMode' as any) || 'is only available in local mode'}
            </div>
          );
        }
        return (
          <div className="space-y-6">
            <APIAndQuotaSettings
              config={config}
              openaiKey={openaiKey}
              anthropicKey={anthropicKey}
              onOpenaiKeyChange={setOpenaiKey}
              onAnthropicKeyChange={setAnthropicKey}
            />
          </div>
        );

      case 'embedding':
        if (mode !== 'local') {
          return (
            <div className="text-sm text-secondary dark:text-gray-400">
              {t('embeddingModel' as any)} {t('availableInLocalMode' as any) || 'is only available in local mode'}
            </div>
          );
        }
        return (
          <div className="space-y-6">
            <EmbeddingSettings />
          </div>
        );

      case 'llm-chat':
        if (mode !== 'local') {
          return (
            <div className="text-sm text-secondary dark:text-gray-400">
              {t('llmChatModel' as any) || 'LLM 推理與對話'} {t('availableInLocalMode' as any) || 'is only available in local mode'}
            </div>
          );
        }
        return (
          <div className="space-y-6">
            <LLMChatSettings />
          </div>
        );


      case 'oauth':
        return (
          <div className="space-y-6">
            <GoogleOAuthSettings />
          </div>
        );

      case 'language-preference':
        return (
          <div className="space-y-6">
            <LanguagePreferencesSettings />
          </div>
        );

      case 'theme-preset':
        return (
          <div className="space-y-6">
            <ThemePresetSettings />
          </div>
        );

      case 'cloud-extension':
        return (
          <div className="space-y-6">
            <CloudExtensionSettings />
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
          <div className="space-y-6">
            <UnsplashFingerprintsSettings />
          </div>
        );

      case 'port-configuration':
        return (
          <div className="space-y-6">
            <PortConfigurationSettings />
          </div>
        );

      default:
        return null;
    }
  };

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
