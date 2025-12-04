'use client';

import React, { useState, useEffect } from 'react';
import { t } from '../../../../lib/i18n';
import { settingsApi } from '../../utils/settingsApi';

interface LanguagePreferencesSettingsProps {
  onLanguageChange?: (language: string) => void;
}

const SUPPORTED_LANGUAGES = [
  { value: 'zh-TW', label: '繁體中文' },
  { value: 'en', label: 'English' },
  { value: 'ja', label: '日本語' },
];

export function LanguagePreferencesSettings({ onLanguageChange }: LanguagePreferencesSettingsProps) {
  const [currentLanguage, setCurrentLanguage] = useState<string>('zh-TW');
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);

  useEffect(() => {
    loadLanguageSetting();
  }, []);

  const loadLanguageSetting = async () => {
    try {
      setLoading(true);
      const setting = await settingsApi.get<{ key: string; value: string; value_type: string }>('/api/v1/system-settings/default_language');
      if (setting && setting.value) {
        setCurrentLanguage(setting.value);
      }
    } catch (err) {
      console.error('Failed to load language setting:', err);
      setError(err instanceof Error ? err.message : 'Failed to load language setting');
    } finally {
      setLoading(false);
    }
  };

  const handleLanguageChange = async (language: string) => {
    try {
      setSaving(true);
      setError(null);
      setSuccess(null);

      await settingsApi.put('/api/v1/system-settings/default_language', language);

      setCurrentLanguage(language);
      setSuccess(t('configSaved') || 'Settings saved successfully');

      if (onLanguageChange) {
        onLanguageChange(language);
      }

      // Clear success message after 3 seconds
      setTimeout(() => setSuccess(null), 3000);
    } catch (err) {
      console.error('Failed to save language setting:', err);
      setError(err instanceof Error ? err.message : 'Failed to save language setting');
    } finally {
      setSaving(false);
    }
  };

  if (loading) {
    return (
      <div className="text-center py-4 text-sm text-gray-500 dark:text-gray-400">
        {t('loading')}
      </div>
    );
  }

  return (
    <div className="space-y-4">
      <div>
        <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
          {t('languagePreference') || '語言偏好'}
        </label>
        <p className="text-sm text-gray-500 dark:text-gray-400 mb-4">
          {t('languagePreferenceDescription') || '設定系統預設語言，新建立的 Workspace 將使用此語言設定'}
        </p>

        {error && (
          <div className="mb-4 p-3 bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 rounded-md text-sm text-red-700 dark:text-red-300">
            {error}
          </div>
        )}

        {success && (
          <div className="mb-4 p-3 bg-green-50 dark:bg-green-900/20 border border-green-200 dark:border-green-800 rounded-md text-sm text-green-700 dark:text-green-300">
            {success}
          </div>
        )}

        <div className="space-y-2">
          {SUPPORTED_LANGUAGES.map((lang) => (
            <label key={lang.value} className="flex items-center">
              <input
                type="radio"
                name="language"
                value={lang.value}
                checked={currentLanguage === lang.value}
                onChange={(e) => handleLanguageChange(e.target.value)}
                disabled={saving}
                className="mr-2"
              />
              <span className="text-gray-900 dark:text-gray-100">{lang.label}</span>
            </label>
          ))}
        </div>
      </div>
    </div>
  );
}

