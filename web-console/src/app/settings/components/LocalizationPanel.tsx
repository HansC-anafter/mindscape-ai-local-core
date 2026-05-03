'use client';

import React from 'react';
import { t } from '../../../lib/i18n';
import { Card } from './Card';
import { InlineAlert } from './InlineAlert';

interface LocalizationPanelProps {
  activeSection?: string;
}

export function LocalizationPanel({ activeSection }: LocalizationPanelProps) {
  const renderSection = () => {
    if (!activeSection) {
      return (
        <div className="text-center py-12 text-gray-500 dark:text-gray-400">
          <p>{t('localization' as any)}</p>
          <p className="text-sm mt-2">{t('selectLocalizationSection' as any) || 'Select a localization feature'}</p>
        </div>
      );
    }

    switch (activeSection) {
      case 'auto-translation':
        return (
          <div className="space-y-6">
            <div>
              <h3 className="text-lg font-medium text-gray-900 dark:text-gray-100 mb-2">{t('autoTranslation' as any)}</h3>
              <p className="text-sm text-gray-600 dark:text-gray-400 mb-4">
                {t('autoTranslationDescription' as any) || 'Use AI to translate i18n keys and keep locales synchronized'}
              </p>
            </div>
            <div className="border border-gray-200 dark:border-gray-700 rounded-lg p-6 bg-gray-50 dark:bg-gray-800">
              <p className="text-sm text-gray-600 dark:text-gray-400">{t('autoTranslationComingSoon' as any) || 'Auto translation is coming soon'}</p>
            </div>
          </div>
        );

      case 'translation-management':
        return (
          <div className="space-y-6">
            <div>
              <h3 className="text-lg font-medium text-gray-900 dark:text-gray-100 mb-2">{t('translationManagement' as any)}</h3>
              <p className="text-sm text-gray-600 dark:text-gray-400 mb-4">
                {t('translationManagementDescription' as any) || 'Manage i18n translation keys and edit localized content'}
              </p>
            </div>
            <div className="border border-gray-200 dark:border-gray-700 rounded-lg p-6 bg-gray-50 dark:bg-gray-800">
              <p className="text-sm text-gray-600 dark:text-gray-400">{t('translationManagementComingSoon' as any) || 'Translation management is coming soon'}</p>
            </div>
          </div>
        );

      default:
        return null;
    }
  };

  return (
    <Card>
      <h2 className="text-xl font-semibold text-gray-900 dark:text-gray-100 mb-4">{t('localization' as any)}</h2>
      {renderSection()}
    </Card>
  );
}
