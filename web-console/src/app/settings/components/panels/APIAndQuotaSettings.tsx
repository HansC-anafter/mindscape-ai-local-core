'use client';

import React from 'react';
import { t } from '../../../../lib/i18n';
import type { BackendConfig } from '../../types';

interface APIAndQuotaSettingsProps {
  config: BackendConfig | null;
  openaiKey: string;
  anthropicKey: string;
  onOpenaiKeyChange: (key: string) => void;
  onAnthropicKeyChange: (key: string) => void;
}

export function APIAndQuotaSettings({
  config,
  openaiKey,
  anthropicKey,
  onOpenaiKeyChange,
  onAnthropicKeyChange,
}: APIAndQuotaSettingsProps) {
  return (
    <div className="space-y-6">
      <div>
        <h3 className="text-sm font-medium text-gray-900 dark:text-gray-100 mb-1">{t('apiAndQuota' as any) || 'API 與配額'}</h3>
        <p className="text-xs text-gray-500 dark:text-gray-400 mb-4">
          {t('apiAndQuotaDescription' as any) || '配置 LLM API 金鑰和管理使用配額'}
        </p>
      </div>

      <div className="space-y-4">
        <div>
          <div className="flex items-center justify-between mb-2">
            <label className="block text-sm font-medium text-gray-700 dark:text-gray-300">
              {t('openaiApiKey' as any)} <span className="text-gray-500 dark:text-gray-400">({t('apiKeyOptional' as any)})</span>
            </label>
            {config?.openai_api_key_configured && (
              <span className="inline-flex items-center gap-1 px-2 py-1 text-xs font-medium text-green-700 dark:text-green-300 bg-green-50 dark:bg-green-900/20 border border-green-200 dark:border-green-800 rounded-md">
                <svg className="w-3 h-3" fill="currentColor" viewBox="0 0 20 20">
                  <path fillRule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zm3.707-9.293a1 1 0 00-1.414-1.414L9 10.586 7.707 9.293a1 1 0 00-1.414 1.414l2 2a1 1 0 001.414 0l4-4z" clipRule="evenodd" />
                </svg>
                {t('configured' as any)}
              </span>
            )}
          </div>
          <input
            type="password"
            value={openaiKey}
            onChange={(e) => onOpenaiKeyChange(e.target.value)}
            placeholder={
              config?.openai_api_key_configured
                ? t('apiKeyConfigured' as any)
                : t('apiKeyPlaceholder' as any)
            }
            className={`w-full px-3 py-2 border rounded-md focus:outline-none focus:ring-2 ${
              config?.openai_api_key_configured
                ? 'border-green-300 dark:border-green-700 bg-green-50 dark:bg-green-900/20 focus:ring-green-500 dark:focus:ring-green-400 text-gray-900 dark:text-gray-100'
                : 'border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-800 focus:ring-gray-500 dark:focus:ring-gray-500 text-gray-900 dark:text-gray-100'
            }`}
          />
          <p className={`mt-1 text-sm ${
            config?.openai_api_key_configured
              ? 'text-green-600 dark:text-green-400 font-medium'
              : 'text-gray-500 dark:text-gray-400'
          }`}>
            {config?.openai_api_key_configured ? t('apiKeyConfigured' as any) : t('apiKeyHint' as any)}
          </p>
        </div>

        <div>
          <div className="flex items-center justify-between mb-2">
            <label className="block text-sm font-medium text-gray-700 dark:text-gray-300">
              {t('anthropicApiKey' as any)} <span className="text-gray-500 dark:text-gray-400">({t('apiKeyOptional' as any)})</span>
            </label>
            {config?.anthropic_api_key_configured && (
              <span className="inline-flex items-center gap-1 px-2 py-1 text-xs font-medium text-green-700 dark:text-green-300 bg-green-50 dark:bg-green-900/20 border border-green-200 dark:border-green-800 rounded-md">
                <svg className="w-3 h-3" fill="currentColor" viewBox="0 0 20 20">
                  <path fillRule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zm3.707-9.293a1 1 0 00-1.414-1.414L9 10.586 7.707 9.293a1 1 0 00-1.414 1.414l2 2a1 1 0 001.414 0l4-4z" clipRule="evenodd" />
                </svg>
                {t('configured' as any)}
              </span>
            )}
          </div>
          <input
            type="password"
            value={anthropicKey}
            onChange={(e) => onAnthropicKeyChange(e.target.value)}
            placeholder={
              config?.anthropic_api_key_configured
                ? t('apiKeyConfigured' as any)
                : t('apiKeyPlaceholder' as any)
            }
            className={`w-full px-3 py-2 border rounded-md focus:outline-none focus:ring-2 ${
              config?.anthropic_api_key_configured
                ? 'border-green-300 dark:border-green-700 bg-green-50 dark:bg-green-900/20 focus:ring-green-500 dark:focus:ring-green-400 text-gray-900 dark:text-gray-100'
                : 'border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-800 focus:ring-gray-500 dark:focus:ring-gray-500 text-gray-900 dark:text-gray-100'
            }`}
          />
          {config?.anthropic_api_key_configured && (
            <p className="mt-1 text-sm text-green-600 dark:text-green-400 font-medium">
              {t('apiKeyConfigured' as any)}
            </p>
          )}
        </div>

        <div className="border-t dark:border-gray-700 pt-4">
          <h4 className="text-xs font-medium text-gray-700 dark:text-gray-300 mb-2">{t('quotaUsage' as any) || '配額使用情況'}</h4>
          <p className="text-xs text-gray-500 dark:text-gray-400">
            {t('quotaUsageDescription' as any) || '配額管理功能即將推出'}
          </p>
        </div>
      </div>
    </div>
  );
}

