'use client';

import React, { useState, useEffect } from 'react';
import { t } from '../../../../lib/i18n';
import { getThemePreset, setThemePreset, type ThemePreset } from '../../../../lib/theme-preset';
import { useTheme } from 'next-themes';

interface ThemePresetSettingsProps {
  onPresetChange?: (preset: ThemePreset) => void;
}

const THEME_PRESETS: { value: ThemePreset; label: string; description: string }[] = [
  {
    value: 'default',
    label: 'Default',
    description: 'Original light mode design with clean, modern aesthetics',
  },
  {
    value: 'warm',
    label: 'Warm',
    description: 'Warm cream and brown tones for a cozy, inviting feel',
  },
];

export function ThemePresetSettings({ onPresetChange }: ThemePresetSettingsProps) {
  const [currentPreset, setCurrentPreset] = useState<ThemePreset>('default');
  const [loading, setLoading] = useState(true);
  const { resolvedTheme } = useTheme();

  useEffect(() => {
    loadPreset();
  }, []);

  const loadPreset = () => {
    try {
      const preset = getThemePreset();
      setCurrentPreset(preset);
    } catch (err) {
      console.error('Failed to load theme preset:', err);
    } finally {
      setLoading(false);
    }
  };

  const handlePresetChange = (preset: ThemePreset) => {
    try {
      // Set preset immediately - this will apply the theme right away
      setThemePreset(preset);
      setCurrentPreset(preset);

      if (onPresetChange) {
        onPresetChange(preset);
      }
    } catch (err) {
      console.error('Failed to save theme preset:', err);
    }
  };

  // Listen for preset changes from other tabs or components
  useEffect(() => {
    const handlePresetChange = () => {
      loadPreset();
    };

    const handleStorageChange = (e: StorageEvent) => {
      if (e.key === 'theme-preset') {
        loadPreset();
      }
    };

    window.addEventListener('theme-preset-changed', handlePresetChange);
    window.addEventListener('storage', handleStorageChange);

    return () => {
      window.removeEventListener('theme-preset-changed', handlePresetChange);
      window.removeEventListener('storage', handleStorageChange);
    };
  }, []);

  if (loading) {
    return (
      <div className="text-center py-4 text-sm text-gray-500 dark:text-gray-400">
        {t('loading' as any)}
      </div>
    );
  }

  // Only show in light mode
  if (resolvedTheme === 'dark') {
    return (
      <div className="space-y-4">
        <div className="p-4 bg-accent-10 dark:bg-blue-900/20 border border-accent/30 dark:border-blue-800 rounded-md">
          <p className="text-sm text-accent dark:text-blue-300">
            {t('themePresetOnlyInLightMode' as any) || 'Theme presets are only available in light mode. Switch to light mode to customize your theme.'}
          </p>
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-4">
      <div>
        <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
          {t('themePreset' as any) || '主題風格'}
        </label>
        <p className="text-sm text-gray-500 dark:text-gray-400 mb-4">
          {t('themePresetDescription' as any) || '選擇日間模式的主題風格。此設定僅在日間模式生效。'}
        </p>

        <div className="space-y-3">
          {THEME_PRESETS.map((preset) => (
            <label
              key={preset.value}
              className={`flex items-start p-4 border-2 rounded-lg cursor-pointer transition-all ${
                currentPreset === preset.value
                  ? 'border-accent bg-accent-10 dark:bg-purple-900/20'
                  : 'border-default dark:border-gray-700 hover:border-default dark:hover:border-gray-600'
              }`}
            >
              <input
                type="radio"
                name="theme-preset"
                value={preset.value}
                checked={currentPreset === preset.value}
                onChange={(e) => handlePresetChange(e.target.value as ThemePreset)}
                className="mt-1 mr-3"
              />
              <div className="flex-1">
                <div className="font-medium text-gray-900 dark:text-gray-100 mb-1">
                  {preset.label}
                </div>
                <div className="text-sm text-gray-500 dark:text-gray-400">
                  {preset.description}
                </div>
              </div>
            </label>
          ))}
        </div>
      </div>
    </div>
  );
}

