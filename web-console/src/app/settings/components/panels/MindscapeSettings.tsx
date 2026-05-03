'use client';

import React from 'react';
import { t } from '../../../../lib/i18n';
import { HabitSuggestionsSettings } from './HabitSuggestionsSettings';
import { ReviewPreferencesSettings } from './ReviewPreferencesSettings';
import type { ReviewPreferences } from '../../types';

interface MindscapeSettingsProps {
  enableHabitSuggestions: boolean;
  reviewPreferences: ReviewPreferences;
  onEnableHabitSuggestionsChange: (enabled: boolean) => void;
  onReviewPreferencesChange: (prefs: Partial<ReviewPreferences>) => void;
}

export function MindscapeSettings({
  enableHabitSuggestions,
  reviewPreferences,
  onEnableHabitSuggestionsChange,
  onReviewPreferencesChange,
}: MindscapeSettingsProps) {
  return (
    <div className="space-y-6">
      <div>
        <h3 className="text-sm font-medium text-gray-900 dark:text-gray-100 mb-1">
          {t('mindscapeConfiguration' as any) || 'Mindscape configuration'}
        </h3>
        <p className="text-xs text-gray-500 dark:text-gray-400 mb-4">
          {t('mindscapeConfigurationDescription' as any) || 'Configure Mindscape behavior and preferences. Additional controls will continue to expand here.'}
        </p>
      </div>

      <div className="border-t dark:border-gray-700 pt-4">
        <HabitSuggestionsSettings
          enabled={enableHabitSuggestions}
          onEnabledChange={onEnableHabitSuggestionsChange}
        />
      </div>

      <div className="border-t pt-6">
        <ReviewPreferencesSettings
          preferences={reviewPreferences}
          onPreferencesChange={onReviewPreferencesChange}
        />
      </div>
    </div>
  );
}
