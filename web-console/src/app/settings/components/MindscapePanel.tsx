'use client';

import React from 'react';
import { t } from '../../../lib/i18n';
import { useBasicSettings } from '../hooks/useBasicSettings';
import { Card } from './Card';
import { InlineAlert } from './InlineAlert';
import { MindscapeSettings } from './panels/MindscapeSettings';

export function MindscapePanel() {
  const {
    loading,
    saving,
    error,
    success,
    enableHabitSuggestions,
    reviewPreferences,
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
        <div className="text-center py-8 text-gray-500 dark:text-gray-400">{t('loading')}</div>
      </Card>
    );
  }

  return (
    <Card>
      <h2 className="text-xl font-semibold text-gray-900 dark:text-gray-100 mb-4">{t('mindscapeConfiguration')}</h2>

      {error && <InlineAlert type="error" message={error} onDismiss={clearError} />}
      {success && <InlineAlert type="success" message={success} onDismiss={clearSuccess} />}

      <form onSubmit={handleSubmit}>
        <div className="space-y-6">
          <MindscapeSettings
            enableHabitSuggestions={enableHabitSuggestions}
            reviewPreferences={reviewPreferences}
            onEnableHabitSuggestionsChange={setEnableHabitSuggestions}
            onReviewPreferencesChange={setReviewPreferences}
          />

          <div className="flex justify-end border-t dark:border-gray-700 pt-4 mt-6">
            <button
              type="submit"
              disabled={saving}
              className="px-4 py-2 bg-gray-600 dark:bg-gray-700 text-white rounded-md hover:bg-gray-700 dark:hover:bg-gray-600 disabled:opacity-50"
            >
              {saving ? t('saving') : t('save')}
            </button>
          </div>
        </div>
      </form>

    </Card>
  );
}

