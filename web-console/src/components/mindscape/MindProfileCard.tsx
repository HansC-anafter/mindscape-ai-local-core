'use client';

import React from 'react';
import { useRouter } from 'next/navigation';
import { t } from '@/lib/i18n';
import { useProfileSummary } from '@/lib/graph-api';

interface MindProfileCardProps {
  profileId?: string;
}

export function MindProfileCard({ profileId }: MindProfileCardProps) {
  const router = useRouter();
  const { summary, isLoading, isError } = useProfileSummary();

  const handleOpenGraph = () => {
    router.push('/mindscape/graph');
  };

  if (isLoading) {
    return (
      <div className="bg-white shadow rounded-lg p-6 mb-6">
        <div className="animate-pulse space-y-4">
          <div className="h-6 bg-gray-200 rounded w-1/3"></div>
          <div className="h-32 bg-gray-100 rounded"></div>
        </div>
      </div>
    );
  }

  if (isError || !summary) {
    return (
      <div className="bg-white shadow rounded-lg p-6 mb-6">
        <p className="text-sm text-gray-500">{t('errorLoadingData' as any)}</p>
      </div>
    );
  }

  return (
    <div className="bg-white shadow rounded-lg p-6 mb-6">
      <h2 className="text-lg font-semibold text-gray-900 mb-4">
        {t('mindProfileCardTitle' as any)}
      </h2>

      <div className="space-y-6">
        {/* Direction Guidance */}
        <div>
          <h3 className="text-sm font-medium text-gray-700 mb-3">
            {t('mindProfileDirectionTitle' as any)}
          </h3>
          <div className="bg-gray-50 rounded-lg p-4 space-y-3">
            {/* Values */}
            <div>
              <span className="text-xs text-gray-500">
                {t('mindProfileValuesLabel' as any)}
              </span>
              <div className="mt-1 flex flex-wrap gap-2">
                {summary.direction.values.length > 0 ? (
                  summary.direction.values.map((value) => (
                    <span
                      key={value.id}
                      className="inline-flex items-center px-2 py-1 bg-white rounded text-sm text-gray-700"
                    >
                      {value.icon} {value.label}
                    </span>
                  ))
                ) : (
                  <span className="text-sm text-gray-400">{t('noData' as any)}</span>
                )}
              </div>
            </div>

            {/* Worldviews */}
            <div>
              <span className="text-xs text-gray-500">
                {t('mindProfileWorldviewsLabel' as any)}
              </span>
              <div className="mt-1 flex flex-wrap gap-2">
                {summary.direction.worldviews.length > 0 ? (
                  summary.direction.worldviews.map((worldview) => (
                    <span
                      key={worldview.id}
                      className="inline-flex items-center px-2 py-1 bg-white rounded text-sm text-gray-700"
                    >
                      {worldview.icon} {worldview.label}
                    </span>
                  ))
                ) : (
                  <span className="text-sm text-gray-400">{t('noData' as any)}</span>
                )}
              </div>
            </div>

            {/* Aesthetics */}
            <div>
              <span className="text-xs text-gray-500">
                {t('mindProfileAestheticsLabel' as any)}
              </span>
              <div className="mt-1 flex flex-wrap gap-2">
                {summary.direction.aesthetics.length > 0 ? (
                  summary.direction.aesthetics.map((aesthetic) => (
                    <span
                      key={aesthetic.id}
                      className="inline-flex items-center px-2 py-1 bg-white rounded text-sm text-gray-700"
                    >
                      {aesthetic.icon} {aesthetic.label}
                    </span>
                  ))
                ) : (
                  <span className="text-sm text-gray-400">{t('noData' as any)}</span>
                )}
              </div>
            </div>

            {/* Knowledge */}
            <div>
              <span className="text-xs text-gray-500">
                {t('mindProfileKnowledgeLabel' as any)}
              </span>
              <div className="mt-1">
                <span className="text-sm text-gray-700">
                  {t('mindProfileKnowledgeCount', {
                    count: summary.direction.knowledge_count.toString(),
                  })}
                </span>
              </div>
            </div>
          </div>
        </div>

        {/* Action Guidance */}
        <div>
          <h3 className="text-sm font-medium text-gray-700 mb-3">
            {t('mindProfileActionTitle' as any)}
          </h3>
          <div className="bg-gray-50 rounded-lg p-4 space-y-2">
            <div>
              <span className="text-xs text-gray-500">
                {t('mindProfileStrategyLabel' as any)}
              </span>
              <div className="mt-1">
                <span className="text-sm text-gray-700">
                  {summary.action.strategies.length > 0
                    ? summary.action.strategies[0].label
                    : t('noData' as any)}
                </span>
              </div>
            </div>
            <div>
              <span className="text-xs text-gray-500">
                {t('mindProfileRoleLabel' as any)}
              </span>
              <div className="mt-1">
                <span className="text-sm text-gray-700">
                  {summary.action.roles.length > 0
                    ? summary.action.roles[0].label
                    : t('noData' as any)}
                </span>
              </div>
            </div>
            <div>
              <span className="text-xs text-gray-500">
                {t('mindProfileRhythmLabel' as any)}
              </span>
              <div className="mt-1">
                <span className="text-sm text-gray-700">
                  {summary.action.rhythms.length > 0
                    ? summary.action.rhythms[0].label
                    : t('noData' as any)}
                </span>
              </div>
            </div>
          </div>
        </div>

        {/* Open Graph Button */}
        <div className="pt-4 border-t border-gray-200">
          <button
            onClick={handleOpenGraph}
            className="w-full px-4 py-2 bg-indigo-600 text-white rounded-lg hover:bg-indigo-700 transition-colors text-sm font-medium"
          >
            {t('mindProfileOpenGraphButton' as any)}
          </button>
        </div>
      </div>
    </div>
  );
}

