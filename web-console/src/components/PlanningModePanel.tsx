'use client';

import React from 'react';
import { t } from '@/lib/i18n';

interface PlanningModePanelProps {
  workspaceId: string;
  apiUrl: string;
}

export default function PlanningModePanel({
  workspaceId,
  apiUrl
}: PlanningModePanelProps) {
  return (
    <div className="p-4 space-y-4">
      <div className="flex items-center gap-2 mb-4">
        <span className="text-2xl">🗓</span>
        <div>
          <h3 className="font-semibold text-gray-900">{t('modePlanning')}</h3>
          <p className="text-xs text-gray-500">{t('modePlanningDescription')}</p>
        </div>
      </div>

      <div className="space-y-3">
        <div className="bg-blue-50 border border-blue-200 rounded-lg p-3">
          <h4 className="text-sm font-medium text-gray-900 mb-2">
            ✅ {t('planningTodayChecklist')}
          </h4>
          <p className="text-xs text-gray-600 mb-2">
            {t('planningTodayChecklistDescription')}
          </p>
          <button className="text-xs text-blue-600 hover:text-blue-700 font-medium">
            {t('viewChecklist')} →
          </button>
        </div>

        <div className="bg-green-50 border border-green-200 rounded-lg p-3">
          <h4 className="text-sm font-medium text-gray-900 mb-2">
            📅 {t('planningWeeklyHighlights')}
          </h4>
          <p className="text-xs text-gray-600 mb-2">
            {t('planningWeeklyHighlightsDescription')}
          </p>
          <button className="text-xs text-green-600 hover:text-green-700 font-medium">
            {t('viewWeeklyHighlights')} →
          </button>
        </div>

        <div className="bg-purple-50 border border-purple-200 rounded-lg p-3">
          <h4 className="text-sm font-medium text-gray-900 mb-2">
            🎯 {t('planningLongTermIntent')}
          </h4>
          <p className="text-xs text-gray-600 mb-2">
            {t('planningLongTermIntentDescription')}
          </p>
          <button className="text-xs text-purple-600 hover:text-purple-700 font-medium">
            {t('viewIntentProgress')} →
          </button>
        </div>
      </div>
    </div>
  );
}
