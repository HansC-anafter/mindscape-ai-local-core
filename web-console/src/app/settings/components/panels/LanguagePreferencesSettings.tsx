'use client';

import React, { useState, useEffect } from 'react';
import {
  useLocaleContext,
  useT,
  type Locale,
} from '../../../../lib/i18n';
import { settingsApi } from '../../utils/settingsApi';

interface LanguagePreferencesSettingsProps {
  onLanguageChange?: (language: string) => void;
}

const SUPPORTED_LANGUAGES = [
  { value: 'zh-TW', label: '繁體中文' },
  { value: 'en', label: 'English' },
  { value: 'ja', label: '日本語' },
] as const;

export function LanguagePreferencesSettings({ onLanguageChange }: LanguagePreferencesSettingsProps) {
  const t = useT();
  const {
    locale,
    setLocale,
    saving: savingUiLocale,
    writable,
    error: uiLocaleError,
  } = useLocaleContext();
  const [systemDefaultLanguage, setSystemDefaultLanguage] =
    useState<Locale>('zh-TW');
  const [loading, setLoading] = useState(true);
  const [savingSystemDefault, setSavingSystemDefault] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);

  useEffect(() => {
    void loadLanguageSetting();
  }, []);

  const loadLanguageSetting = async () => {
    try {
      setLoading(true);
      const setting = await settingsApi.get<{ key: string; value: string; value_type: string }>('/api/v1/system-settings/default_language');
      if (
        setting
        && SUPPORTED_LANGUAGES.some(({ value }) => value === setting.value)
      ) {
        setSystemDefaultLanguage(setting.value as Locale);
      }
    } catch (err) {
      console.error('Failed to load language setting:', err);
      setError(err instanceof Error ? err.message : 'Failed to load language setting');
    } finally {
      setLoading(false);
    }
  };

  const handleUiLanguageChange = async (language: Locale) => {
    try {
      setError(null);
      setSuccess(null);
      await setLocale(language);
      setSuccess(t('configSaved' as any));
      onLanguageChange?.(language);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to save UI language');
    }
  };

  const handleSystemDefaultChange = async (language: Locale) => {
    try {
      setSavingSystemDefault(true);
      setError(null);
      setSuccess(null);
      await settingsApi.put('/api/v1/system-settings/default_language', language);
      setSystemDefaultLanguage(language);
      setSuccess(t('configSaved' as any));
    } catch (err) {
      console.error('Failed to save language setting:', err);
      setError(err instanceof Error ? err.message : 'Failed to save language setting');
    } finally {
      setSavingSystemDefault(false);
    }
  };

  if (loading) {
    return (
      <div className="text-center py-4 text-sm text-gray-500 dark:text-gray-400">
        {t('loading' as any)}
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {(error || uiLocaleError) && (
        <div className="p-3 bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 rounded-md text-sm text-red-700 dark:text-red-300">
          {error || uiLocaleError}
        </div>
      )}

      {success && (
        <div className="p-3 bg-green-50 dark:bg-green-900/20 border border-green-200 dark:border-green-800 rounded-md text-sm text-green-700 dark:text-green-300">
          {success}
        </div>
      )}

      <div>
        <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
          {t('uiLanguageTitle' as any)}
        </label>
        <p className="text-sm text-gray-500 dark:text-gray-400 mb-4">
          {t('uiLanguageDescription' as any)}
        </p>
        <div className="space-y-2">
          {SUPPORTED_LANGUAGES.map((lang) => (
            <label key={lang.value} className="flex items-center">
              <input
                type="radio"
                name="ui-language"
                value={lang.value}
                checked={locale === lang.value}
                onChange={() => void handleUiLanguageChange(lang.value)}
                disabled={savingUiLocale || !writable}
                className="mr-2"
              />
              <span className="text-gray-900 dark:text-gray-100">{lang.label}</span>
            </label>
          ))}
        </div>
      </div>

      <div className="border-t border-gray-200 pt-6 dark:border-gray-700">
        <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
          {t('systemDefaultUiLanguageTitle' as any)}
        </label>
        <p className="text-sm text-gray-500 dark:text-gray-400 mb-4">
          {t('systemDefaultUiLanguageDescription' as any)}
        </p>
        <div className="space-y-2">
          {SUPPORTED_LANGUAGES.map((lang) => (
            <label key={lang.value} className="flex items-center">
              <input
                type="radio"
                name="system-default-ui-language"
                value={lang.value}
                checked={systemDefaultLanguage === lang.value}
                onChange={() => void handleSystemDefaultChange(lang.value)}
                disabled={savingSystemDefault}
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
