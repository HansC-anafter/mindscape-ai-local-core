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
          <p className="text-sm mt-2">{t('selectLocalizationSection' as any) || '請選擇一個本地化功能'}</p>
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
                {t('autoTranslationDescription' as any) || '使用 AI 自動翻譯 i18n 鍵值，支援多語系同步'}
              </p>
            </div>
            <div className="border border-gray-200 dark:border-gray-700 rounded-lg p-6 bg-gray-50 dark:bg-gray-800">
              <p className="text-sm text-gray-600 dark:text-gray-400">{t('autoTranslationComingSoon' as any) || '自動翻譯功能即將推出'}</p>
            </div>
          </div>
        );

      case 'translation-management':
        return (
          <div className="space-y-6">
            <div>
              <h3 className="text-lg font-medium text-gray-900 dark:text-gray-100 mb-2">{t('translationManagement' as any)}</h3>
              <p className="text-sm text-gray-600 dark:text-gray-400 mb-4">
                {t('translationManagementDescription' as any) || '管理 i18n 翻譯鍵值，查看和編輯多語系內容'}
              </p>
            </div>
            <div className="border border-gray-200 dark:border-gray-700 rounded-lg p-6 bg-gray-50 dark:bg-gray-800">
              <p className="text-sm text-gray-600 dark:text-gray-400">{t('translationManagementComingSoon' as any) || '翻譯管理功能即將推出'}</p>
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

