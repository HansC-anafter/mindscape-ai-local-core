'use client';

import React from 'react';
import { t } from '../../../../lib/i18n';

interface HabitSuggestionsSettingsProps {
  enabled: boolean;
  onEnabledChange: (enabled: boolean) => void;
}

export function HabitSuggestionsSettings({
  enabled,
  onEnabledChange,
}: HabitSuggestionsSettingsProps) {
  return (
    <div>
      <h3 className="text-sm font-medium text-gray-700 dark:text-gray-300 mb-4">{t('habitSuggestions')}</h3>
      <div className="space-y-3">
        <label className="flex items-start">
          <input
            type="checkbox"
            checked={enabled}
            onChange={(e) => onEnabledChange(e.target.checked)}
            className="mt-1 mr-3"
          />
          <div>
            <span className="font-medium text-gray-900 dark:text-gray-100">{t('enableHabitSuggestions')}</span>
            <p className="text-sm text-gray-500 dark:text-gray-400 mt-1">
              {t('enableHabitSuggestionsDescription')}
            </p>
            <p className="text-xs text-gray-400 dark:text-gray-500 mt-1">
              {enabled
                ? t('habitSuggestionsEnabled')
                : t('habitSuggestionsDisabled')}
            </p>
          </div>
        </label>
      </div>
    </div>
  );
}

