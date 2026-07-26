import React from 'react';
import { useT, type Translator } from '../../lib/i18n';
import type { CurrentMode, MindscapeIntent, MindscapeProfile, MindscapeSuggestion } from './mindscapePageTypes';

interface MindscapeOverviewPanelsProps {
  isOnboarding: boolean;
  hasState: boolean;
  currentMode: CurrentMode | null;
  suggestions: MindscapeSuggestion[];
  profile: MindscapeProfile | null;
  intents: MindscapeIntent[];
  onEditSelfIntro: () => void;
  onAcceptSuggestion: (suggestion: MindscapeSuggestion) => void;
  onDismissSuggestion: (suggestion: MindscapeSuggestion) => void;
}

export function MindscapeOverviewPanels({
  isOnboarding,
  hasState,
  currentMode,
  suggestions,
  profile,
  intents,
  onEditSelfIntro,
  onAcceptSuggestion,
  onDismissSuggestion,
}: MindscapeOverviewPanelsProps) {
  const t = useT();
  return (
    <>
      {!isOnboarding && !hasState && currentMode && (
        <div className="bg-gradient-to-r from-gray-50 to-blue-50 border-2 border-gray-200 rounded-lg p-6 mb-6">
          <h2 className="text-lg font-semibold text-gray-900 mb-4">{t('mindscapeCurrentState' as any)}</h2>
          <div className="space-y-2">
            <div>
              <span className="text-sm font-medium text-gray-700">{t('currentMainMode' as any)}</span>
              <span className="ml-2 text-sm text-gray-900 font-semibold">{currentMode.mainMode}</span>
            </div>
            <div>
              <span className="text-sm font-medium text-gray-700">本週聚焦：</span>
              <div className="ml-2 inline-flex flex-wrap gap-2">
                {currentMode.weeklyFocus.map((focus, idx) => (
                  <span key={idx} className="px-2 py-1 bg-white rounded text-sm text-gray-700">
                    {focus}
                  </span>
                ))}
              </div>
            </div>
            <div>
              <span className="text-sm font-medium text-gray-700">AI 會優先協助：</span>
              <div className="ml-2 inline-flex flex-wrap gap-2">
                {currentMode.aiAssistants.map((assistant, idx) => (
                  <span key={idx} className="px-2 py-1 bg-white rounded text-sm text-gray-700">
                    {assistant}
                  </span>
                ))}
              </div>
            </div>
          </div>
          <button className="mt-4 px-4 py-2 bg-gray-600 text-white rounded-md hover:bg-gray-700 text-sm">
            調整模式
          </button>
        </div>
      )}

      {suggestions.length > 0 && (
        <div className="bg-yellow-50 border-2 border-yellow-200 rounded-lg p-6 mb-6 min-w-0">
          <div className="flex items-center mb-4 min-w-0">
            <span className="text-2xl mr-2 flex-shrink-0">🔍</span>
            <h2 className="text-lg font-semibold text-gray-900 min-w-0 break-words">
              {t('mindscapeSuggestions', { count: suggestions.length.toString() })}
            </h2>
          </div>
          <div className="space-y-3">
            {suggestions.map((suggestion) => (
              <div key={suggestion.id} className="bg-white rounded-lg p-4 border border-yellow-300 min-w-0">
                <div className="flex items-start justify-between gap-4 min-w-0">
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center mb-2 flex-wrap gap-2">
                      <span className="text-xs px-2 py-1 bg-yellow-100 text-yellow-800 rounded flex-shrink-0">
                        {suggestion.type === 'project' ? t('longTermProject' as any) :
                          suggestion.type === 'principle' ? t('designPrinciple' as any) :
                            suggestion.type === 'preference' ? t('preferences' as any) : t('intents' as any)}
                      </span>
                      <span className="text-xs text-gray-500 flex-shrink-0">{suggestion.source}</span>
                      <span className="text-xs text-gray-400 flex-shrink-0">
                        {t('confidence' as any)}{Math.round(suggestion.confidence * 100)}%
                      </span>
                    </div>
                    <h3 className="font-medium text-gray-900 mb-1 break-words">
                      {formatSuggestionTitle(suggestion.title, t)}
                    </h3>
                    <p className="text-sm text-gray-600 break-words">
                      {formatSuggestionDescription(suggestion.description, t)}
                    </p>
                  </div>
                  <div className="ml-4 flex space-x-2 flex-shrink-0">
                    <button
                      onClick={() => onAcceptSuggestion(suggestion)}
                      className="px-3 py-1 bg-green-600 text-white rounded text-sm hover:bg-green-700 whitespace-nowrap"
                    >
                      {t('accept' as any)}
                    </button>
                    <button
                      onClick={() => onDismissSuggestion(suggestion)}
                      className="px-3 py-1 bg-gray-300 text-gray-700 rounded text-sm hover:bg-gray-400 whitespace-nowrap"
                    >
                      {t('skip' as any)}
                    </button>
                  </div>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {!isOnboarding && !hasState && (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
          <div className="bg-white shadow rounded-lg p-6">
            <h3 className="text-lg font-semibold text-gray-900 mb-2">開局角色卡</h3>
            <div className="text-sm text-gray-600 mb-4">
              {profile?.self_description ? (
                <>
                  <div className="mb-2">
                    <span className="font-medium">現在在做：</span>
                    <span className="ml-2">{profile.self_description.identity}</span>
                  </div>
                  <div className="mb-2">
                    <span className="font-medium">想搞定的：</span>
                    <span className="ml-2">{profile.self_description.solving}</span>
                  </div>
                  <div className="mb-2">
                    <span className="font-medium">在思考的：</span>
                    <span className="ml-2">{profile.self_description.thinking}</span>
                  </div>
                </>
              ) : (
                <span className="text-gray-400">尚未設定</span>
              )}
            </div>
            <button
              onClick={onEditSelfIntro}
              className="px-4 py-2 bg-blue-600 text-white rounded-md hover:bg-blue-700 text-sm"
            >
              編輯
            </button>
          </div>

          <div className="bg-white shadow rounded-lg p-6">
            <h3 className="text-lg font-semibold text-gray-900 mb-2">長線任務追蹤</h3>
            <div className="text-sm text-gray-600 mb-4">
              {intents.length > 0 ? (
                <>
                  <div className="mb-2">
                    <span className="font-medium">{t('inProgress' as any)}</span>
                    <span className="ml-2">{intents.filter(i => i.status === 'active').length} {t('items' as any)}</span>
                  </div>
                  <div className="mb-2">
                    <span className="font-medium">{t('completed' as any)}</span>
                    <span className="ml-2">{intents.filter(i => i.status === 'completed').length} {t('items' as any)}</span>
                  </div>
                </>
              ) : (
                <span className="text-gray-400">{t('noLongTermTasks' as any)}</span>
              )}
            </div>
            <button className="px-4 py-2 bg-blue-600 text-white rounded-md hover:bg-blue-700 text-sm">
              {t('viewAll' as any)}
            </button>
          </div>

          <div className="bg-white shadow rounded-lg p-6">
            <h3 className="text-lg font-semibold text-gray-900 mb-2">{t('workRhythmSettings' as any)}</h3>
            <div className="text-sm text-gray-600 mb-4">
              <div className="mb-2">
                <span className="font-medium">{t('preferredRhythm' as any)}</span>
                <span className="ml-2 text-gray-400">{t('extractingSuggestions' as any)}</span>
              </div>
              <div className="mb-2">
                <span className="font-medium">{t('commonTools' as any)}</span>
                <span className="ml-2 text-gray-400">{t('toolsWordPressNotion' as any)}</span>
              </div>
            </div>
            <button className="px-4 py-2 bg-blue-600 text-white rounded-md hover:bg-blue-700 text-sm">
              {t('viewDetails' as any)}
            </button>
          </div>
        </div>
      )}

      <div className="mt-8 bg-blue-50 border border-blue-200 rounded-lg p-4">
        <p className="text-sm text-blue-800">
          <strong>{t('mindscapeNote' as any).split('：')[0]}：</strong> {t('mindscapeNote' as any).split('：').slice(1).join('：')}
        </p>
      </div>
    </>
  );
}

function formatSuggestionTitle(title: string, t: Translator) {
  if (!title) return title;
  if (title.startsWith('suggestion.') || title.startsWith('suggestions.')) {
    const keyMatch = title.match(/^(suggestion\.|suggestions\.)(\S+)\s+(.+)$/);
    if (keyMatch) {
      const fullKey = keyMatch[1] + keyMatch[2];
      const restText = keyMatch[3];
      const translated = t(fullKey as any);
      return translated !== fullKey ? `${translated} ${restText}` : title;
    }
    return t(title as any) || title;
  }
  return title;
}

function formatSuggestionDescription(description: string, t: Translator) {
  if (!description) return description;
  if (description.startsWith('suggestion.') || description.startsWith('suggestions.')) {
    return t(description as any) || description;
  }
  return description;
}
