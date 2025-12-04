'use client';

import React from 'react';
import { t } from '../../../../lib/i18n';
import type { BackendConfig } from '../../types';

interface LLMAPIKeySettingsProps {
  config: BackendConfig | null;
  openaiKey: string;
  anthropicKey: string;
  onOpenaiKeyChange: (key: string) => void;
  onAnthropicKeyChange: (key: string) => void;
}

export function LLMAPIKeySettings({
  config,
  openaiKey,
  anthropicKey,
  onOpenaiKeyChange,
  onAnthropicKeyChange,
}: LLMAPIKeySettingsProps) {
  return (
    <div className="space-y-4">
      <h3 className="text-sm font-medium text-gray-700 mb-4">{t('llmApiKeyConfig')}</h3>

      <div>
        <div className="flex items-center justify-between mb-2">
          <label className="block text-sm font-medium text-gray-700">
            {t('openaiApiKey')} <span className="text-gray-500">({t('apiKeyOptional')})</span>
          </label>
          {config?.openai_api_key_configured && (
            <span className="inline-flex items-center gap-1 px-2 py-1 text-xs font-medium text-green-700 bg-green-50 border border-green-200 rounded-md">
              <svg className="w-3 h-3" fill="currentColor" viewBox="0 0 20 20">
                <path fillRule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zm3.707-9.293a1 1 0 00-1.414-1.414L9 10.586 7.707 9.293a1 1 0 00-1.414 1.414l2 2a1 1 0 001.414 0l4-4z" clipRule="evenodd" />
              </svg>
              {t('configured')}
            </span>
          )}
        </div>
        <input
          type="password"
          value={openaiKey}
          onChange={(e) => onOpenaiKeyChange(e.target.value)}
          placeholder={
            config?.openai_api_key_configured
              ? t('apiKeyConfigured')
              : t('apiKeyPlaceholder')
          }
          className={`w-full px-3 py-2 border rounded-md focus:outline-none focus:ring-2 ${
            config?.openai_api_key_configured
              ? 'border-green-300 bg-green-50 focus:ring-green-500'
              : 'border-gray-300 focus:ring-gray-500'
          }`}
        />
        <p className={`mt-1 text-sm ${
          config?.openai_api_key_configured
            ? 'text-green-600 font-medium'
            : 'text-gray-500'
        }`}>
          {config?.openai_api_key_configured ? t('apiKeyConfigured') : t('apiKeyHint')}
        </p>
      </div>

      <div>
        <div className="flex items-center justify-between mb-2">
          <label className="block text-sm font-medium text-gray-700">
            {t('anthropicApiKey')} <span className="text-gray-500">({t('apiKeyOptional')})</span>
          </label>
          {config?.anthropic_api_key_configured && (
            <span className="inline-flex items-center gap-1 px-2 py-1 text-xs font-medium text-green-700 bg-green-50 border border-green-200 rounded-md">
              <svg className="w-3 h-3" fill="currentColor" viewBox="0 0 20 20">
                <path fillRule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zm3.707-9.293a1 1 0 00-1.414-1.414L9 10.586 7.707 9.293a1 1 0 00-1.414 1.414l2 2a1 1 0 001.414 0l4-4z" clipRule="evenodd" />
              </svg>
              {t('configured')}
            </span>
          )}
        </div>
        <input
          type="password"
          value={anthropicKey}
          onChange={(e) => onAnthropicKeyChange(e.target.value)}
          placeholder={
            config?.anthropic_api_key_configured
              ? t('apiKeyConfigured')
              : t('apiKeyPlaceholder')
          }
          className={`w-full px-3 py-2 border rounded-md focus:outline-none focus:ring-2 ${
            config?.anthropic_api_key_configured
              ? 'border-green-300 bg-green-50 focus:ring-green-500'
              : 'border-gray-300 focus:ring-gray-500'
          }`}
        />
        {config?.anthropic_api_key_configured && (
          <p className="mt-1 text-sm text-green-600 font-medium">
            {t('apiKeyConfigured')}
          </p>
        )}
      </div>
    </div>
  );
}

