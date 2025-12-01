'use client';

import React from 'react';
import { t } from '@/lib/i18n';

interface FileInfo {
  name: string;
  pages?: number;
  language: string;
  detected_type: string;
  size?: number;
}

interface CollaborationResult {
  enabled: boolean;
  themes?: string[];
  intents?: string[];
  suggested_steps?: number;
  today_actions?: number;
  suggested_formats?: string[];
  action?: string;
  error?: string;
  reason?: string;
}

interface CollaborationResults {
  semantic_seeds: CollaborationResult;
  daily_planning: CollaborationResult;
  content_drafting: CollaborationResult;
}

interface MultiAICollaborationCardProps {
  fileInfo: FileInfo;
  collaborationResults: CollaborationResults;
  onSelectPath: (path: CollaborationPath) => void;
}

interface CollaborationPath {
  type: 'semantic_seeds' | 'daily_planning' | 'content_drafting';
  action: string;
  data?: any;
}

export default function MultiAICollaborationCard({
  fileInfo,
  collaborationResults,
  onSelectPath
}: MultiAICollaborationCardProps) {
  const handlePathSelect = (type: 'semantic_seeds' | 'daily_planning' | 'content_drafting') => {
    const result = collaborationResults[type];
    if (result.enabled && result.action) {
      onSelectPath({
        type,
        action: result.action,
        data: result
      });
    }
  };

  return (
    <div
      className="bg-blue-50 border-2 border-blue-200 rounded-lg p-4 shadow-sm w-full max-w-full"
      style={{
        minHeight: '200px',
        position: 'relative',
        zIndex: 1,
        display: 'block',
        visibility: 'visible',
        opacity: 1,
        boxSizing: 'border-box',
        overflow: 'hidden'
      }}
    >
      <div className="flex items-start gap-3 mb-4">
        <div className="flex-shrink-0">
          <div className="w-10 h-10 bg-blue-100 rounded-full flex items-center justify-center">
            <svg className="w-6 h-6 text-blue-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M17 20h5v-2a3 3 0 00-5.356-1.857M17 20H7m10 0v-2c0-.656-.126-1.283-.356-1.857M7 20H2v-2a3 3 0 015.356-1.857M7 20v-2c0-.656.126-1.283.356-1.857m0 0a5.002 5.002 0 019.288 0M15 7a3 3 0 11-6 0 3 3 0 016 0zm6 3a2 2 0 11-4 0 2 2 0 014 0zM7 10a2 2 0 11-4 0 2 2 0 014 0z" />
            </svg>
          </div>
        </div>
              <div className="flex-1 min-w-0">
                <h3 className="font-semibold text-gray-900 mb-1">
                  🤝 {t('multiAICollaborationTitle')}
                </h3>
                <p className="text-sm text-gray-600 mb-2 break-words">
                  {t('fileReceived')}：<span className="font-medium break-all">{fileInfo.name}</span>
                  {fileInfo.pages && `（${fileInfo.pages} ${t('pages')}）`}
                </p>
                <p className="text-xs text-gray-500 break-words">
                  {t('mainLanguage')}：{fileInfo.language === 'zh-TW' ? t('traditionalChinese') : t('english')} ·
                  {t('fileLooksLike')} {fileInfo.detected_type === 'proposal' ? t('proposalOrPlan') : fileInfo.detected_type}
                </p>
              </div>
      </div>

      <div className="space-y-3">
        <p className="text-sm font-medium text-gray-700">
          {t('aiTeamPreview')}
        </p>

        {/* Semantic Seeds Path */}
        {collaborationResults.semantic_seeds.enabled && (
          <div className="bg-white rounded-lg p-3 border border-blue-200">
            <div className="flex items-start justify-between gap-2">
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-2 mb-1">
                  <span className="text-lg">🧩</span>
                  <span className="font-medium text-gray-900">{t('extractHighlightsAndIntent')}</span>
                </div>
                {collaborationResults.semantic_seeds.themes && collaborationResults.semantic_seeds.themes.length > 0 && (
                  <div className="text-sm text-gray-600 mb-1 break-words">
                    {t('mainThemes')}：{collaborationResults.semantic_seeds.themes.join(' / ')}
                  </div>
                )}
                {collaborationResults.semantic_seeds.intents && collaborationResults.semantic_seeds.intents.length > 0 && (
                  <div className="text-sm text-gray-600 break-words">
                    {t('possibleLongTermIntent')}：<span className="font-medium">{collaborationResults.semantic_seeds.intents[0]}</span>
                  </div>
                )}
              </div>
              <button
                onClick={() => handlePathSelect('semantic_seeds')}
                className="ml-3 px-4 py-2 bg-blue-600 text-white text-sm font-medium rounded-lg hover:bg-blue-700 transition-colors whitespace-nowrap flex-shrink-0"
              >
                {t('addToMindscape')}
              </button>
            </div>
          </div>
        )}

        {/* Daily Planning Path */}
        {collaborationResults.daily_planning.enabled && (
          <div className="bg-white rounded-lg p-3 border border-blue-200">
            <div className="flex items-start justify-between gap-2">
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-2 mb-1">
                  <span className="text-lg">🗓</span>
                  <span className="font-medium text-gray-900">{t('convertToTaskList')}</span>
                </div>
                {collaborationResults.daily_planning.suggested_steps && (
                  <div className="text-sm text-gray-600 break-words">
                    {t('suggestedSteps')} {collaborationResults.daily_planning.suggested_steps} {t('steps')}{t('comma')}
                    {collaborationResults.daily_planning.today_actions && (
                      <>{t('todayCanDo')} {collaborationResults.daily_planning.today_actions} {t('items')}</>
                    )}
                  </div>
                )}
              </div>
              <button
                onClick={() => handlePathSelect('daily_planning')}
                className="ml-3 px-4 py-2 bg-blue-600 text-white text-sm font-medium rounded-lg hover:bg-blue-700 transition-colors whitespace-nowrap flex-shrink-0"
              >
                {t('viewTaskList')}
              </button>
            </div>
          </div>
        )}

        {/* Content Drafting Path */}
        {collaborationResults.content_drafting.enabled && (
          <div className="bg-white rounded-lg p-3 border border-blue-200">
            <div className="flex items-start justify-between gap-2">
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-2 mb-1">
                  <span className="text-lg">✍️</span>
                  <span className="font-medium text-gray-900">{t('extendToContentDraft')}</span>
                </div>
                {collaborationResults.content_drafting.suggested_formats && (
                  <div className="text-sm text-gray-600 break-words">
                    {t('canBecome')}：{collaborationResults.content_drafting.suggested_formats.join(' / ')}
                  </div>
                )}
              </div>
              <div className="ml-3 flex gap-2 flex-shrink-0">
                <button
                  onClick={() => handlePathSelect('content_drafting')}
                  className="px-4 py-2 bg-blue-600 text-white text-sm font-medium rounded-lg hover:bg-blue-700 transition-colors whitespace-nowrap"
                >
                  {t('createDraft')} {collaborationResults.content_drafting.suggested_formats?.[0] || ''}
                </button>
                <button
                  onClick={() => handlePathSelect('content_drafting')}
                  className="px-3 py-2 bg-gray-200 text-gray-700 text-sm font-medium rounded-lg hover:bg-gray-300 transition-colors whitespace-nowrap"
                >
                  {t('viewSummary')}
                </button>
              </div>
            </div>
          </div>
        )}

        {!collaborationResults.semantic_seeds.enabled &&
         !collaborationResults.daily_planning.enabled &&
         !collaborationResults.content_drafting.enabled && (
          <div className="text-sm text-gray-500 text-center py-2">
            {t('cannotAnalyzeFileType')}
          </div>
        )}
      </div>
    </div>
  );
}
