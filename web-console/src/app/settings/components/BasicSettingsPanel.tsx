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
              <div className="text-center py-4 text-sm text-gray-500 dark:text-gray-400">{t('loading')}</div>
            ) : (
              <>
                <BackendModeSettings mode={mode} onModeChange={setMode} />
                {mode === 'remote_crs' && (
                  <div className="border-t dark:border-gray-700 pt-6 space-y-4">
                    <div>
                      <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
                        {t('serviceUrl')} <span className="text-red-500">*</span>
                      </label>
                      <input
                        type="text"
                        value={remoteUrl}
                        onChange={(e) => setRemoteUrl(e.target.value)}
                        placeholder="https://your-agent-service.example.com"
                        className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-md focus:outline-none focus:ring-2 focus:ring-gray-500 dark:focus:ring-gray-500 bg-white dark:bg-gray-800 text-gray-900 dark:text-gray-100"
                        required
                      />
                    </div>

                    <div>
                      <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
                        {t('apiToken')} <span className="text-red-500">*</span>
                      </label>
                      <input
                        type="password"
                        value={remoteToken}
                        onChange={(e) => setRemoteToken(e.target.value)}
                        placeholder={
                          config?.remote_crs_configured
                            ? t('tokenPlaceholderConfigured')
                            : t('tokenPlaceholder')
                        }
                        className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-md focus:outline-none focus:ring-2 focus:ring-gray-500 dark:focus:ring-gray-500 bg-white dark:bg-gray-800 text-gray-900 dark:text-gray-100"
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
            <div className="text-center py-4 text-sm text-gray-500">{t('loading')}</div>
          );
        }
        if (mode !== 'local') {
          return (
            <div className="text-sm text-gray-500 dark:text-gray-400">
              {t('apiAndQuota') || 'API 與配額'} {t('availableInLocalMode') || 'is only available in local mode'}
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
            <div className="text-sm text-gray-500 dark:text-gray-400">
              {t('embeddingModel')} {t('availableInLocalMode') || 'is only available in local mode'}
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
            <div className="text-sm text-gray-500 dark:text-gray-400">
              {t('llmChatModel') || 'LLM 推理與對話'} {t('availableInLocalMode') || 'is only available in local mode'}
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
              {saving ? t('saving') : t('save')}
            </button>
        </div>
      </form>
    </Card>
  );
}
