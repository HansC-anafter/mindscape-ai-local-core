'use client';

import React from 'react';
import { t } from '../../../../lib/i18n';
import type { ReviewPreferences } from '../../types';

const dayOfWeekOptions = [
  { value: 0, key: 'dayOfWeekMonday' as const },
  { value: 1, key: 'dayOfWeekTuesday' as const },
  { value: 2, key: 'dayOfWeekWednesday' as const },
  { value: 3, key: 'dayOfWeekThursday' as const },
  { value: 4, key: 'dayOfWeekFriday' as const },
  { value: 5, key: 'dayOfWeekSaturday' as const },
  { value: 6, key: 'dayOfWeekSunday' as const },
];

interface ReviewPreferencesSettingsProps {
  preferences: ReviewPreferences;
  onPreferencesChange: (prefs: Partial<ReviewPreferences>) => void;
}

export function ReviewPreferencesSettings({
  preferences,
  onPreferencesChange,
}: ReviewPreferencesSettingsProps) {
  return (
    <div>
      <h3 className="text-sm font-medium text-gray-700 dark:text-gray-300 mb-4">{t('reviewPreferences' as any)}</h3>
      <div className="space-y-4">
        <div>
          <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
            {t('reviewCadence' as any)}
          </label>
          <select
            value={preferences.cadence}
            onChange={(e) =>
              onPreferencesChange({
                cadence: e.target.value as 'manual' | 'weekly' | 'monthly',
              })
            }
            className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-md focus:outline-none focus:ring-2 focus:ring-gray-500 dark:focus:ring-gray-500 bg-white dark:bg-gray-800 text-gray-900 dark:text-gray-100"
          >
            <option value="manual">{t('reviewCadenceManual' as any)}</option>
            <option value="weekly">{t('reviewCadenceWeekly' as any)}</option>
            <option value="monthly">{t('reviewCadenceMonthly' as any)}</option>
          </select>
          <p className="text-xs text-gray-500 dark:text-gray-400 mt-1">{t('reviewCadenceDescription' as any)}</p>
        </div>

        {preferences.cadence === 'weekly' && (
          <div>
            <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
              {t('reviewDayOfWeek' as any)}
            </label>
            <select
              value={preferences.day_of_week ?? 6}
              onChange={(e) =>
                onPreferencesChange({ day_of_week: parseInt(e.target.value) })
              }
              className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-md focus:outline-none focus:ring-2 focus:ring-gray-500 dark:focus:ring-gray-500 bg-white dark:bg-gray-800 text-gray-900 dark:text-gray-100"
            >
              {dayOfWeekOptions.map((option) => (
                <option key={option.value} value={option.value}>
                  {t(option.key)}
                </option>
              ))}
            </select>
          </div>
        )}

        {preferences.cadence === 'monthly' && (
          <div>
            <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
              {t('reviewDayOfMonth' as any)}
            </label>
            <input
              type="number"
              min="1"
              max="31"
              value={preferences.day_of_month ?? 28}
              onChange={(e) =>
                onPreferencesChange({
                  day_of_month: parseInt(e.target.value) || 28,
                })
              }
              className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-md focus:outline-none focus:ring-2 focus:ring-gray-500 dark:focus:ring-gray-500 bg-white dark:bg-gray-800 text-gray-900 dark:text-gray-100"
            />
          </div>
        )}

        {preferences.cadence !== 'manual' && (
          <>
            <div>
              <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
                {t('reviewTimeOfDay' as any)}
              </label>
              <input
                type="time"
                value={preferences.time_of_day || '21:00'}
                onChange={(e) =>
                  onPreferencesChange({ time_of_day: e.target.value })
                }
                className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-md focus:outline-none focus:ring-2 focus:ring-gray-500 dark:focus:ring-gray-500 bg-white dark:bg-gray-800 text-gray-900 dark:text-gray-100"
              />
            </div>

            <div>
              <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
                {t('reviewMinEntries' as any)}
              </label>
              <input
                type="number"
                min="1"
                value={preferences.min_entries ?? 10}
                onChange={(e) =>
                  onPreferencesChange({
                    min_entries: parseInt(e.target.value) || 10,
                  })
                }
                className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-md focus:outline-none focus:ring-2 focus:ring-gray-500 dark:focus:ring-gray-500 bg-white dark:bg-gray-800 text-gray-900 dark:text-gray-100"
              />
              <p className="text-xs text-gray-500 mt-1">{t('reviewMinEntriesDescription' as any)}</p>
            </div>

            <div>
              <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
                {t('reviewMinInsightEvents' as any)}
              </label>
              <input
                type="number"
                min="0"
                value={preferences.min_insight_events ?? 3}
                onChange={(e) =>
                  onPreferencesChange({
                    min_insight_events: parseInt(e.target.value) || 3,
                  })
                }
                className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-md focus:outline-none focus:ring-2 focus:ring-gray-500 dark:focus:ring-gray-500 bg-white dark:bg-gray-800 text-gray-900 dark:text-gray-100"
              />
              <p className="text-xs text-gray-500 mt-1">
                {t('reviewMinInsightEventsDescription' as any)}
              </p>
            </div>
          </>
        )}
      </div>
    </div>
  );
}

