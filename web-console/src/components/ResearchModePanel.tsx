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
          <h3 className="font-semibold text-gray-900">{t('modeResearch' as any)}</h3>
          <p className="text-xs text-gray-500">{t('modeResearchDescription' as any)}</p>
        </div>
      </div>

      <div className="space-y-3">
        <div className="bg-blue-50 border border-blue-200 rounded-lg p-3">
          <h4 className="text-sm font-medium text-gray-900 mb-2">
            📚 {t('researchLiteratureSummary' as any)}
          </h4>
          <p className="text-xs text-gray-600 mb-2">
            {t('researchLiteratureSummaryDescription' as any)}
          </p>
          <button className="text-xs text-blue-600 hover:text-blue-700 font-medium">
            {t('generateSummary' as any)} →
          </button>
        </div>

        <div className="bg-green-50 border border-green-200 rounded-lg p-3">
          <h4 className="text-sm font-medium text-gray-900 mb-2">
            ❓ {t('researchQuestions' as any)}
          </h4>
          <p className="text-xs text-gray-600 mb-2">
            {t('researchQuestionsDescription' as any)}
          </p>
          <button className="text-xs text-green-600 hover:text-green-700 font-medium">
            {t('extractQuestions' as any)} →
          </button>
        </div>

        <div className="bg-gray-50 border border-gray-200 rounded-lg p-3">
          <h4 className="text-sm font-medium text-gray-900 mb-2">
            📝 {t('obsidianVaultIntegration' as any)}
          </h4>
          <p className="text-xs text-gray-600 mb-2">
            {t('obsidianVaultIntegrationDescription' as any)}
          </p>
          <button className="text-xs text-gray-600 hover:text-gray-700 font-medium">
            {t('syncToObsidian' as any)} →
          </button>
        </div>
      </div>
    </div>
  );
}
