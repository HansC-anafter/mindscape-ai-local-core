'use client';

import React from 'react';
import { t } from '../../../lib/i18n';
import { useBasicSettings } from '../hooks/useBasicSettings';
import { Card } from './Card';
import { InlineAlert } from './InlineAlert';
import { StatusPill } from './StatusPill';
import { LLMModelSettings } from './LLMModelSettings';
import { GoogleOAuthSettings } from './GoogleOAuthSettings';
import type { BackendInfo } from '../types';

const dayOfWeekOptions = [
  { value: 0, key: 'dayOfWeekMonday' as const },
  { value: 1, key: 'dayOfWeekTuesday' as const },
  { value: 2, key: 'dayOfWeekWednesday' as const },
  { value: 3, key: 'dayOfWeekThursday' as const },
  { value: 4, key: 'dayOfWeekFriday' as const },
  { value: 5, key: 'dayOfWeekSaturday' as const },
  { value: 6, key: 'dayOfWeekSunday' as const },
];

export function BasicSettingsPanel() {
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
    enableHabitSuggestions,
    reviewPreferences,
    setMode,
    setRemoteUrl,
    setRemoteToken,
    setOpenaiKey,
    setAnthropicKey,
    setEnableHabitSuggestions,
    setReviewPreferences,
    saveSettings,
    clearError,
    clearSuccess,
  } = useBasicSettings();

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    await saveSettings();
  };

  if (loading) {
    return (
      <Card>
        <div className="text-center py-8">{t('loading')}</div>
      </Card>
    );
  }

  return (
    <Card>
      <h2 className="text-xl font-semibold text-gray-900 mb-4">{t('basicSettings')}</h2>

      {error && <InlineAlert type="error" message={error} onDismiss={clearError} />}
      {success && <InlineAlert type="success" message={success} onDismiss={clearSuccess} />}

      <form onSubmit={handleSubmit}>
        <div className="space-y-6">
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-2">
              {t('backendMode')}
            </label>
            <div className="space-y-2">
              <label className="flex items-center">
                <input
                  type="radio"
                  name="mode"
                  value="local"
                  checked={mode === 'local'}
                  onChange={(e) => setMode(e.target.value)}
                  className="mr-2"
                />
                <div>
                  <span className="font-medium">{t('localLLM')}</span>
                  <p className="text-sm text-gray-500">{t('localLLMDescription')}</p>
                </div>
              </label>
              <label className="flex items-center">
                <input
                  type="radio"
                  name="mode"
                  value="remote_crs"
                  checked={mode === 'remote_crs'}
                  onChange={(e) => setMode(e.target.value)}
                  className="mr-2"
                />
                <div>
                  <span className="font-medium">{t('remoteAgentService')}</span>
                  <p className="text-sm text-gray-500">{t('remoteAgentServiceDescription')}</p>
                </div>
              </label>
            </div>
          </div>

          {mode === 'local' && (
            <div className="border-t pt-6 space-y-6">
              <div className="space-y-4">
                <h3 className="text-sm font-medium text-gray-700 mb-4">{t('llmApiKeyConfig')}</h3>

                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-2">
                    {t('openaiApiKey')} <span className="text-gray-500">({t('apiKeyOptional')})</span>
                  </label>
                  <input
                    type="password"
                    value={openaiKey}
                    onChange={(e) => setOpenaiKey(e.target.value)}
                    placeholder={
                      config?.openai_api_key_configured
                        ? t('apiKeyConfigured')
                        : t('apiKeyPlaceholder')
                    }
                    className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-purple-500"
                  />
                  <p className="mt-1 text-sm text-gray-500">
                    {config?.openai_api_key_configured ? t('apiKeyConfigured') : t('apiKeyHint')}
                  </p>
                </div>

                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-2">
                    {t('anthropicApiKey')} <span className="text-gray-500">({t('apiKeyOptional')})</span>
                  </label>
                  <input
                    type="password"
                    value={anthropicKey}
                    onChange={(e) => setAnthropicKey(e.target.value)}
                    placeholder={
                      config?.anthropic_api_key_configured
                        ? t('apiKeyConfigured')
                        : t('apiKeyPlaceholder')
                    }
                    className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-purple-500"
                  />
                </div>
              </div>

              <div className="border-t pt-6">
                <h3 className="text-sm font-medium text-gray-700 mb-4">{t('modelConfiguration')}</h3>
                <LLMModelSettings />
              </div>
            </div>
          )}

          {mode === 'remote_crs' && (
            <div className="border-t pt-6 space-y-4">
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-2">
                  {t('serviceUrl')} <span className="text-red-500">*</span>
                </label>
                <input
                  type="text"
                  value={remoteUrl}
                  onChange={(e) => setRemoteUrl(e.target.value)}
                  placeholder="https://your-agent-service.example.com"
                  className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-purple-500"
                  required
                />
              </div>

              <div>
                <label className="block text-sm font-medium text-gray-700 mb-2">
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
                  className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-purple-500"
                  required
                />
              </div>
            </div>
          )}

          <div className="border-t pt-6">
            <h3 className="text-sm font-medium text-gray-700 mb-4">{t('habitSuggestions')}</h3>
            <div className="space-y-3">
              <label className="flex items-start">
                <input
                  type="checkbox"
                  checked={enableHabitSuggestions}
                  onChange={(e) => setEnableHabitSuggestions(e.target.checked)}
                  className="mt-1 mr-3"
                />
                <div>
                  <span className="font-medium text-gray-900">{t('enableHabitSuggestions')}</span>
                  <p className="text-sm text-gray-500 mt-1">
                    {t('enableHabitSuggestionsDescription')}
                  </p>
                  <p className="text-xs text-gray-400 mt-1">
                    {enableHabitSuggestions
                      ? t('habitSuggestionsEnabled')
                      : t('habitSuggestionsDisabled')}
                  </p>
                </div>
              </label>
            </div>
          </div>

          <div className="border-t pt-6">
            <h3 className="text-sm font-medium text-gray-700 mb-4">{t('reviewPreferences')}</h3>
            <div className="space-y-4">
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-2">
                  {t('reviewCadence')}
                </label>
                <select
                  value={reviewPreferences.cadence}
                  onChange={(e) =>
                    setReviewPreferences({
                      cadence: e.target.value as 'manual' | 'weekly' | 'monthly',
                    })
                  }
                  className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-purple-500"
                >
                  <option value="manual">{t('reviewCadenceManual')}</option>
                  <option value="weekly">{t('reviewCadenceWeekly')}</option>
                  <option value="monthly">{t('reviewCadenceMonthly')}</option>
                </select>
                <p className="text-xs text-gray-500 mt-1">{t('reviewCadenceDescription')}</p>
              </div>

              {reviewPreferences.cadence === 'weekly' && (
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-2">
                    {t('reviewDayOfWeek')}
                  </label>
                  <select
                    value={reviewPreferences.day_of_week ?? 6}
                    onChange={(e) =>
                      setReviewPreferences({ day_of_week: parseInt(e.target.value) })
                    }
                    className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-purple-500"
                  >
                    {dayOfWeekOptions.map((option) => (
                      <option key={option.value} value={option.value}>
                        {t(option.key)}
                      </option>
                    ))}
                  </select>
                </div>
              )}

              {reviewPreferences.cadence === 'monthly' && (
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-2">
                    {t('reviewDayOfMonth')}
                  </label>
                  <input
                    type="number"
                    min="1"
                    max="31"
                    value={reviewPreferences.day_of_month ?? 28}
                    onChange={(e) =>
                      setReviewPreferences({
                        day_of_month: parseInt(e.target.value) || 28,
                      })
                    }
                    className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-purple-500"
                  />
                </div>
              )}

              {reviewPreferences.cadence !== 'manual' && (
                <>
                  <div>
                    <label className="block text-sm font-medium text-gray-700 mb-2">
                      {t('reviewTimeOfDay')}
                    </label>
                    <input
                      type="time"
                      value={reviewPreferences.time_of_day || '21:00'}
                      onChange={(e) =>
                        setReviewPreferences({ time_of_day: e.target.value })
                      }
                      className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-purple-500"
                    />
                  </div>

                  <div>
                    <label className="block text-sm font-medium text-gray-700 mb-2">
                      {t('reviewMinEntries')}
                    </label>
                    <input
                      type="number"
                      min="1"
                      value={reviewPreferences.min_entries ?? 10}
                      onChange={(e) =>
                        setReviewPreferences({
                          min_entries: parseInt(e.target.value) || 10,
                        })
                      }
                      className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-purple-500"
                    />
                    <p className="text-xs text-gray-500 mt-1">{t('reviewMinEntriesDescription')}</p>
                  </div>

                  <div>
                    <label className="block text-sm font-medium text-gray-700 mb-2">
                      {t('reviewMinInsightEvents')}
                    </label>
                    <input
                      type="number"
                      min="0"
                      value={reviewPreferences.min_insight_events ?? 3}
                      onChange={(e) =>
                        setReviewPreferences({
                          min_insight_events: parseInt(e.target.value) || 3,
                        })
                      }
                      className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-purple-500"
                    />
                    <p className="text-xs text-gray-500 mt-1">
                      {t('reviewMinInsightEventsDescription')}
                    </p>
                  </div>
                </>
              )}
            </div>
          </div>

          {config && (
            <div className="border-t pt-4">
              <h3 className="text-sm font-medium text-gray-700 mb-2">{t('backendStatus')}</h3>
              <div className="space-y-2 text-sm">
                {Object.entries(config.available_backends).map(([key, info]) => (
                  <div key={key} className="flex items-center justify-between">
                    <span className="text-gray-600">{info.name}</span>
                    <StatusPill
                      status={info.available ? 'enabled' : 'disabled'}
                      label={info.available ? t('available') : t('notConfigured')}
                    />
                  </div>
                ))}
              </div>
            </div>
          )}

          <div className="border-t pt-6">
            <h3 className="text-lg font-medium text-gray-900 mb-4">OAuth Integration</h3>
            <GoogleOAuthSettings />
          </div>

          <div className="flex justify-end border-t pt-4">
            <button
              type="submit"
              disabled={saving}
              className="px-4 py-2 bg-purple-600 text-white rounded-md hover:bg-purple-700 disabled:opacity-50"
            >
              {saving ? t('saving') : t('save')}
            </button>
          </div>
        </div>
      </form>
    </Card>
  );
}
