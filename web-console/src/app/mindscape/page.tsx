'use client';

import React, { useState, useEffect } from 'react';
import { useRouter } from 'next/navigation';
import Header from '../../components/Header';
import OnboardingBanner from '../../components/OnboardingBanner';
import SelfIntroDialog from '../../components/SelfIntroDialog';
import TaskCard from '../../components/TaskCard';
import HabitSuggestionToast from '../../components/HabitSuggestionToast';
import { t } from '../../lib/i18n';

const API_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';

interface OnboardingState {
  task1_completed: boolean;
  task2_completed: boolean;
  task3_completed: boolean;
  task1_completed_at?: string;
  task2_completed_at?: string;
  task3_completed_at?: string;
}

interface MindscapeSuggestion {
  id: string;
  type: 'project' | 'principle' | 'preference' | 'intent';
  title: string;
  description: string;
  source: string;
  confidence: number;
}

interface CurrentMode {
  mainMode: string;
  weeklyFocus: string[];
  aiAssistants: string[];
}

export default function MindscapePage() {
  const router = useRouter();
  const [onboardingState, setOnboardingState] = useState<OnboardingState | null>(null);
  const [showSelfIntroDialog, setShowSelfIntroDialog] = useState(false);
  const [showCongrats, setShowCongrats] = useState(false);
  const [currentMode, setCurrentMode] = useState<CurrentMode | null>(null);
  const [suggestions, setSuggestions] = useState<MindscapeSuggestion[]>([]);
  const [profile, setProfile] = useState<any>(null);
  const [intents, setIntents] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);

  const profileId = 'default-user';
  const apiUrl = API_URL.startsWith('http') ? API_URL : '';

  useEffect(() => {
    loadAllData();
  }, []);

  const loadAllData = async () => {
    try {
      setLoading(true);
      await Promise.all([
        loadOnboardingStatus(),
        loadMindscapeData()
      ]);
    } catch (err) {
      console.error('Failed to load data:', err);
    } finally {
      setLoading(false);
    }
  };

  const loadOnboardingStatus = async () => {
    try {
      const response = await fetch(`${apiUrl}/api/v1/mindscape/onboarding/status?profile_id=${profileId}`);
      if (response.ok) {
        const data = await response.json();
        setOnboardingState(data.onboarding_state);

        // Check if just completed all tasks
        const completedCount = [
          data.onboarding_state.task1_completed,
          data.onboarding_state.task2_completed,
          data.onboarding_state.task3_completed,
        ].filter(Boolean).length;

        if (completedCount === 3 && !localStorage.getItem('mindscape_congrats_shown')) {
          setShowCongrats(true);
          localStorage.setItem('mindscape_congrats_shown', 'true');
        }
      }
    } catch (err) {
      console.error('Failed to load onboarding status:', err);
    }
  };

  const loadMindscapeData = async () => {
    try {
      // Load profile
      try {
        const profileRes = await fetch(`${apiUrl}/api/v1/mindscape/profiles/${profileId}`);
        if (profileRes.ok) {
          const profileData = await profileRes.json();
          setProfile(profileData);
        }
      } catch (err) {
        console.log('Profile not found, will use defaults');
      }

      // Load intents
      try {
        const intentsRes = await fetch(`${apiUrl}/api/v1/mindscape/profiles/${profileId}/intents`);
        if (intentsRes.ok) {
          const intentsData = await intentsRes.json();
          setIntents(intentsData);
        }
      } catch (err) {
        console.log('Intents not found');
      }

      // Load current mode
      try {
        const modeRes = await fetch(`${apiUrl}/api/v1/mindscape/profiles/${profileId}/current-mode`);
        if (modeRes.ok) {
          const modeData = await modeRes.json();
          setCurrentMode({
            mainMode: modeData.main_mode || '未設定',
            weeklyFocus: modeData.weekly_focus || [],
            aiAssistants: modeData.ai_assistants || []
          });
        }
      } catch (err) {
        console.log('Failed to load current mode');
        setCurrentMode({
          mainMode: '未設定',
          weeklyFocus: [],
          aiAssistants: []
        });
      }

      // Load suggestions
      try {
        const suggestionsRes = await fetch(`${apiUrl}/api/v1/mindscape/suggestions?profile_id=${profileId}&status=pending`);
        if (suggestionsRes.ok) {
          const suggestionsData = await suggestionsRes.json();
          const formattedSuggestions = suggestionsData.suggestions.map((s: any) => ({
            id: s.id,
            type: s.suggestion_type,
            title: s.title,
            description: s.description,
            source: s.source_summary || '最近使用記錄',
            confidence: s.confidence || 0.5
          }));
          setSuggestions(formattedSuggestions);
        }
      } catch (err) {
        console.log('Failed to load suggestions');
      }
    } catch (err) {
      console.error('Failed to load mindscape data:', err);
    }
  };

  // Handle Task 1: Self Introduction
  const handleCompleteSelfIntro = async (data: { identity: string; solving: string; thinking: string }) => {
    try {
      const response = await fetch(`${apiUrl}/api/v1/mindscape/onboarding/self-intro?profile_id=${profileId}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(data)
      });

      if (response.ok) {
        await loadAllData();
        alert(t('setupCompleteAlert'));
      } else {
        throw new Error('Failed to complete self intro');
      }
    } catch (err: any) {
      console.error('Failed to complete self intro:', err);
      throw err;
    }
  };

  const handleAcceptSuggestion = async (suggestion: MindscapeSuggestion) => {
    try {
      const response = await fetch(`${apiUrl}/api/v1/mindscape/suggestions/${suggestion.id}/review?action=accept`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' }
      });

      if (response.ok) {
        setSuggestions(suggestions.filter(s => s.id !== suggestion.id));
        alert(`已接受建議：${suggestion.title}`);
        loadMindscapeData();
      } else {
        throw new Error('Failed to accept suggestion');
      }
    } catch (err: any) {
      alert(`接受建議失敗：${err.message}`);
    }
  };

  const handleDismissSuggestion = async (suggestion: MindscapeSuggestion) => {
    try {
      const response = await fetch(`${apiUrl}/api/v1/mindscape/suggestions/${suggestion.id}/review?action=dismiss`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' }
      });

      if (response.ok) {
        setSuggestions(suggestions.filter(s => s.id !== suggestion.id));
      } else {
        throw new Error('Failed to dismiss suggestion');
      }
    } catch (err: any) {
      alert(`略過建議失敗：${err.message}`);
    }
  };

  const getCompletionCount = () => {
    if (!onboardingState) return 0;
    return [
      onboardingState.task1_completed,
      onboardingState.task2_completed,
      onboardingState.task3_completed,
    ].filter(Boolean).length;
  };

  const isOnboarding = onboardingState && (
    !onboardingState.task1_completed
  );

  if (loading) {
    return (
      <div className="min-h-screen bg-gray-50">
        <Header />
        <main className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
          <div className="text-center py-12">
            <p className="text-gray-600">{t('loading')}</p>
          </div>
        </main>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-gray-50">
      <Header />
      <main className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
        {/* Page Title */}
        <div className="mb-8">
          <h1 className="text-3xl font-bold text-gray-900 mb-2">{t('navMindscape')}</h1>
          <p className="text-gray-600">
            {t('mindscapePageDescription')}
          </p>
        </div>

        {/* Onboarding Banner (show if any task is incomplete) */}
        {(isOnboarding || (onboardingState && (!onboardingState.task2_completed || !onboardingState.task3_completed))) && (
          <OnboardingBanner
            completedCount={getCompletionCount()}
            totalCount={3}
            showCongrats={showCongrats}
            onClose={() => setShowCongrats(false)}
            task1Completed={onboardingState?.task1_completed || false}
            task2Completed={onboardingState?.task2_completed || false}
            task3Completed={onboardingState?.task3_completed || false}
          />
        )}

        {/* Self Intro Dialog */}
        <SelfIntroDialog
          isOpen={showSelfIntroDialog}
          onClose={() => setShowSelfIntroDialog(false)}
          onSubmit={handleCompleteSelfIntro}
        />

        {/* Onboarding Task Cards (show if task 1 not complete OR if task1 complete but user wants to see task 2/3) */}
        {(isOnboarding || (onboardingState && (!onboardingState.task2_completed || !onboardingState.task3_completed))) && (
          <div className="grid grid-cols-1 md:grid-cols-3 gap-6 mb-8">
            {/* Task 1: Self Intro */}
            <TaskCard
              taskNumber={1}
              title={t('roleCardTitle')}
              subtitle={t('onboardingTask1Subtitle')}
              isCompleted={onboardingState?.task1_completed || false}
              footerText={t('onboardingTask1Footer')}
              completedContent={
                profile?.self_description ? (
                  <div className="text-sm text-gray-700 space-y-2">
                    <p>{t('aiWillUseThisPerspective')}</p>
                    <ul className="list-disc list-inside space-y-1">
                      <li><strong>{t('currentlyDoing')}</strong>{profile.self_description.identity}</li>
                      <li><strong>{t('tryingToSolve')}</strong>{profile.self_description.solving}</li>
                      <li><strong>{t('thinking')}</strong>{profile.self_description.thinking}</li>
                    </ul>
                  </div>
                ) : null
              }
              uncompletedContent={
                <ul className="text-sm text-gray-700 space-y-1 list-disc list-inside">
                  <li>{t('whatAreYouMainlyDoing')}</li>
                  <li>{t('whatDoYouWantToSolve')}</li>
                  <li>{t('whatAreYouThinking')}</li>
                </ul>
              }
              buttonText={onboardingState?.task1_completed ? t('editButton') : t('quickSetup')}
              onButtonClick={() => {
                if (onboardingState?.task1_completed) {
                  setShowSelfIntroDialog(true);
                } else {
                  router.push('/intro');
                }
              }}
            />

            {/* Task 2: First Project */}
            <TaskCard
              taskNumber={2}
              title={t('firstLongTermTask')}
              subtitle={t('onboardingTask2Subtitle')}
              isCompleted={onboardingState?.task2_completed || false}
              isBlocked={!onboardingState?.task1_completed}
              blockMessage={t('taskBlockMessage')}
              footerText={t('onboardingTask2Footer')}
              completedContent={
                intents.length > 0 ? (
                  <div className="text-sm text-gray-700 space-y-2">
                    <p className="mb-2">{t('aiWillUpdateProjectStatus')}</p>
                    {intents.slice(0, 2).map((intent) => (
                      <div key={intent.id} className="flex items-start">
                        <span className="mr-2">📋</span>
                        <div>
                          <p className="font-medium">{intent.title}</p>
                          <p className="text-xs text-gray-500">{t('lastUpdated')}{new Date(intent.updated_at).toLocaleDateString('zh-TW')}</p>
                        </div>
                      </div>
                    ))}
                  </div>
                ) : null
              }
              uncompletedContent={
                <ul className="text-sm text-gray-700 space-y-1 list-disc list-inside">
                  <li>{t('tellUsOneThingYouWantToPush')}</li>
                  <li>{t('aiWillBreakItDown')}</li>
                  <li>{t('autoCreateFirstIntent')}</li>
                </ul>
              }
              buttonText={onboardingState?.task2_completed ? t('onboardingTask2ButtonCompleted') : t('onboardingTask2ButtonUncompleted')}
              onButtonClick={() => {
                if (onboardingState?.task2_completed) {
                  // Navigate to playbooks filtered by project tag
                  window.location.href = '/playbooks?tags=project';
                } else {
                  // Navigate to playbook detail page for onboarding
                  window.location.href = '/playbooks/project_breakdown_onboarding?onboarding=task2';
                }
              }}
            />

            {/* Task 3: Work Rhythm */}
            <TaskCard
              taskNumber={3}
              title={t('onboardingTask3Title')}
              subtitle={t('onboardingTask3Subtitle')}
              isCompleted={onboardingState?.task3_completed || false}
              isBlocked={!onboardingState?.task1_completed}
              blockMessage={t('taskBlockMessage')}
              footerText={t('onboardingTask3Footer')}
              completedContent={
                <div className="text-sm text-gray-700 space-y-2">
                  <p>{t('aiWillUseThesePreferences')}</p>
                  <p><strong>{t('preferredRhythm')}</strong>{t('morningFocusImportantTasks')}</p>
                  <p><strong>{t('commonTools')}</strong>{t('toolsWordPressNotion')}</p>
                </div>
              }
              uncompletedContent={
                <div>
                  <ul className="text-sm text-gray-700 space-y-1 list-disc list-inside">
                    <li>{t('whatThreeThingsThisWeek')}</li>
                    <li>{t('whatToolsDoYouUse')}</li>
                    <li>{t('whatWorkRhythmDoYouLike')}</li>
                  </ul>
                  <div className="mt-3 p-2 bg-blue-50 rounded text-xs text-blue-800">
                    {t('onboardingTask3WordPressHint')}
                  </div>
                </div>
              }
              buttonText={onboardingState?.task3_completed ? t('onboardingTask3ButtonCompleted') : t('onboardingTask3ButtonUncompleted')}
              onButtonClick={() => {
                if (onboardingState?.task3_completed) {
                  // Navigate to playbooks filtered by planning tag
                  window.location.href = '/playbooks?tags=planning';
                } else {
                  // Navigate to playbook detail page for onboarding
                  window.location.href = '/playbooks/weekly_review_onboarding?onboarding=task3';
                }
              }}
            />
          </div>
        )}

        {/* Current Mode Overview (only show after onboarding complete) */}
        {!isOnboarding && currentMode && (
          <div className="bg-gradient-to-r from-purple-50 to-blue-50 border-2 border-purple-200 rounded-lg p-6 mb-6">
            <h2 className="text-lg font-semibold text-gray-900 mb-4">{t('mindscapeCurrentState')}</h2>
            <div className="space-y-2">
              <div>
                <span className="text-sm font-medium text-gray-700">{t('currentMainMode')}</span>
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
            <button className="mt-4 px-4 py-2 bg-purple-600 text-white rounded-md hover:bg-purple-700 text-sm">
              調整模式
            </button>
          </div>
        )}

        {/* AI Suggestions */}
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
                          {suggestion.type === 'project' ? t('longTermProject') :
                           suggestion.type === 'principle' ? t('designPrinciple') :
                           suggestion.type === 'preference' ? t('preferences') : t('intents')}
                        </span>
                        <span className="text-xs text-gray-500 flex-shrink-0">{suggestion.source}</span>
                        <span className="text-xs text-gray-400 flex-shrink-0">
                          {t('confidence')}{Math.round(suggestion.confidence * 100)}%
                        </span>
                      </div>
                      <h3 className="font-medium text-gray-900 mb-1 break-words">
                        {(() => {
                          const title = suggestion.title;
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
                        })()}
                      </h3>
                      <p className="text-sm text-gray-600 break-words">
                        {(() => {
                          const desc = suggestion.description;
                          if (!desc) return desc;
                          if (desc.startsWith('suggestion.') || desc.startsWith('suggestions.')) {
                            return t(desc as any) || desc;
                          }
                          return desc;
                        })()}
                      </p>
                    </div>
                    <div className="ml-4 flex space-x-2 flex-shrink-0">
                      <button
                        onClick={() => handleAcceptSuggestion(suggestion)}
                        className="px-3 py-1 bg-green-600 text-white rounded text-sm hover:bg-green-700 whitespace-nowrap"
                      >
                        {t('accept')}
                      </button>
                      <button
                        onClick={() => handleDismissSuggestion(suggestion)}
                        className="px-3 py-1 bg-gray-300 text-gray-700 rounded text-sm hover:bg-gray-400 whitespace-nowrap"
                      >
                        {t('skip')}
                      </button>
                    </div>
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Established Mindscape Cards (only show after onboarding) */}
        {!isOnboarding && (
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
            {/* Self Settings Card */}
            <div className="bg-white shadow rounded-lg p-6">
              <h3 className="text-lg font-semibold text-gray-900 mb-2">開局角色卡</h3>
              <p className="text-sm text-gray-600 mb-4">
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
              </p>
              <button
                onClick={() => setShowSelfIntroDialog(true)}
                className="px-4 py-2 bg-blue-600 text-white rounded-md hover:bg-blue-700 text-sm"
              >
                編輯
              </button>
            </div>

            {/* Intent Cards */}
            <div className="bg-white shadow rounded-lg p-6">
              <h3 className="text-lg font-semibold text-gray-900 mb-2">長線任務追蹤</h3>
              <p className="text-sm text-gray-600 mb-4">
                {intents.length > 0 ? (
                  <>
                    <div className="mb-2">
                      <span className="font-medium">{t('inProgress')}</span>
                      <span className="ml-2">{intents.filter(i => i.status === 'active').length} {t('items')}</span>
                    </div>
                    <div className="mb-2">
                      <span className="font-medium">{t('completed')}</span>
                      <span className="ml-2">{intents.filter(i => i.status === 'completed').length} {t('items')}</span>
                    </div>
                  </>
                ) : (
                  <span className="text-gray-400">{t('noLongTermTasks')}</span>
                )}
              </p>
              <button className="px-4 py-2 bg-blue-600 text-white rounded-md hover:bg-blue-700 text-sm">
                {t('viewAll')}
              </button>
            </div>

            {/* Work Mode */}
            <div className="bg-white shadow rounded-lg p-6">
              <h3 className="text-lg font-semibold text-gray-900 mb-2">{t('workRhythmSettings')}</h3>
              <p className="text-sm text-gray-600 mb-4">
                <div className="mb-2">
                  <span className="font-medium">{t('preferredRhythm')}</span>
                  <span className="ml-2 text-gray-400">{t('extractingSuggestions')}</span>
                </div>
                <div className="mb-2">
                  <span className="font-medium">{t('commonTools')}</span>
                  <span className="ml-2 text-gray-400">{t('toolsWordPressNotion')}</span>
                </div>
              </p>
              <button className="px-4 py-2 bg-blue-600 text-white rounded-md hover:bg-blue-700 text-sm">
                {t('viewDetails')}
              </button>
            </div>
          </div>
        )}

        {/* Footer Note */}
        <div className="mt-8 bg-blue-50 border border-blue-200 rounded-lg p-4">
          <p className="text-sm text-blue-800">
            <strong>{t('mindscapeNote').split('：')[0]}：</strong> {t('mindscapeNote').split('：').slice(1).join('：')}
          </p>
        </div>
      </main>

      {/* Habit Suggestion Toast */}
      <HabitSuggestionToast
        profileId={profileId}
        autoShow={true}
        checkInterval={30000} // 30 秒檢查一次
      />
    </div>
  );
}
