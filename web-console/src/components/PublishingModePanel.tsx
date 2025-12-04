'use client';

import React from 'react';
import { t } from '@/lib/i18n';

interface PublishingModePanelProps {
  workspaceId: string;
  apiUrl: string;
}

export default function PublishingModePanel({
  workspaceId,
  apiUrl
}: PublishingModePanelProps) {
  return (
    <div className="p-4 space-y-4">
      <div className="flex items-center gap-2 mb-4">
        <span className="text-2xl">✍️</span>
        <div>
          <h3 className="font-semibold text-gray-900">{t('modePublishing')}</h3>
          <p className="text-xs text-gray-500">{t('modePublishingDescription')}</p>
        </div>
      </div>

      <div className="space-y-3">
        <div className="bg-blue-50 border border-blue-200 rounded-lg p-3">
          <h4 className="text-sm font-medium text-gray-900 mb-2">
            📦 {t('publishingVersionTree')}
          </h4>
          <p className="text-xs text-gray-600 mb-2">
            {t('publishingVersionTreeDescription')}
          </p>
          <button className="text-xs text-blue-600 hover:text-blue-700 font-medium">
            {t('viewVersions')} →
          </button>
        </div>

        <div className="bg-green-50 border border-green-200 rounded-lg p-3">
          <h4 className="text-sm font-medium text-gray-900 mb-2">
            🚀 {t('publishingWordPress')}
          </h4>
          <p className="text-xs text-gray-600 mb-2">
            {t('publishingWordPressDescription')}
          </p>
          <button className="text-xs text-green-600 hover:text-green-700 font-medium">
            {t('publishToWordPress')} →
          </button>
        </div>

        <div className="bg-gray-50 border border-gray-200 rounded-lg p-3">
          <h4 className="text-sm font-medium text-gray-900 mb-2">
            📄 {t('publishingMarkdownExport')}
          </h4>
          <p className="text-xs text-gray-600 mb-2">
            {t('publishingMarkdownExportDescription')}
          </p>
          <button className="text-xs text-gray-600 hover:text-gray-700 font-medium">
            {t('exportMarkdown')} →
          </button>
        </div>

        <div className="bg-orange-50 border border-orange-200 rounded-lg p-3">
          <h4 className="text-sm font-medium text-gray-900 mb-2">
            🌐 {t('publishingI18nCheck')}
          </h4>
          <p className="text-xs text-gray-600 mb-2">
            {t('publishingI18nCheckDescription')}
          </p>
          <button className="text-xs text-orange-600 hover:text-orange-700 font-medium">
            {t('checkI18n')} →
          </button>
        </div>
      </div>
    </div>
  );
}
