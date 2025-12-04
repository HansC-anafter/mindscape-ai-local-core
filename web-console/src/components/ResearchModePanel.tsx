'use client';

import React from 'react';
import { t } from '@/lib/i18n';

interface ResearchModePanelProps {
  workspaceId: string;
  apiUrl: string;
}

export default function ResearchModePanel({
  workspaceId,
  apiUrl
}: ResearchModePanelProps) {
  return (
    <div className="p-4 space-y-4">
      <div className="flex items-center gap-2 mb-4">
        <span className="text-2xl">🔬</span>
        <div>
          <h3 className="font-semibold text-gray-900">{t('modeResearch')}</h3>
          <p className="text-xs text-gray-500">{t('modeResearchDescription')}</p>
        </div>
      </div>

      <div className="space-y-3">
        <div className="bg-blue-50 border border-blue-200 rounded-lg p-3">
          <h4 className="text-sm font-medium text-gray-900 mb-2">
            📚 {t('researchLiteratureSummary')}
          </h4>
          <p className="text-xs text-gray-600 mb-2">
            {t('researchLiteratureSummaryDescription')}
          </p>
          <button className="text-xs text-blue-600 hover:text-blue-700 font-medium">
            {t('generateSummary')} →
          </button>
        </div>

        <div className="bg-green-50 border border-green-200 rounded-lg p-3">
          <h4 className="text-sm font-medium text-gray-900 mb-2">
            ❓ {t('researchQuestions')}
          </h4>
          <p className="text-xs text-gray-600 mb-2">
            {t('researchQuestionsDescription')}
          </p>
          <button className="text-xs text-green-600 hover:text-green-700 font-medium">
            {t('extractQuestions')} →
          </button>
        </div>

        <div className="bg-gray-50 border border-gray-200 rounded-lg p-3">
          <h4 className="text-sm font-medium text-gray-900 mb-2">
            📝 {t('obsidianVaultIntegration')}
          </h4>
          <p className="text-xs text-gray-600 mb-2">
            {t('obsidianVaultIntegrationDescription')}
          </p>
          <button className="text-xs text-gray-600 hover:text-gray-700 font-medium">
            {t('syncToObsidian')} →
          </button>
        </div>
      </div>
    </div>
  );
}
