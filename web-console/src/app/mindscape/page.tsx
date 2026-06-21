'use client';

import React, { useEffect, useState } from 'react';
import { useRouter } from 'next/navigation';
import Header from '../../components/Header';
import OnboardingBanner from '../../components/OnboardingBanner';
import SelfIntroDialog from '../../components/SelfIntroDialog';
import HabitSuggestionToast from '../../components/HabitSuggestionToast';
import { MindProfileCard } from '../../components/mindscape/MindProfileCard';
import { t } from '../../lib/i18n';
import { getApiBaseUrl } from '../../lib/api-url';
import {
  DAILY_PLANNING_INTENT_PAYLOAD,
  buildContentDraftingIntentPayload,
  completeSelfIntro,
  createMindscapeIntent,
  fetchCurrentMode,
  fetchFirstWorkspace,
  fetchMindscapeIntents,
  fetchMindscapeProfile,
  fetchOnboardingStatus,
  fetchPendingSuggestions,
  reviewSuggestion,
} from './mindscapePageApi';
import { MindscapeEpisodePanel } from './MindscapeEpisodePanel';
import { MindscapeOnboardingTasks } from './MindscapeOnboardingTasks';
import { MindscapeOverviewPanels } from './MindscapeOverviewPanels';
import type { CurrentMode, MindscapeIntent, MindscapeProfile, MindscapeSuggestion, OnboardingState, SelfIntroPayload } from './mindscapePageTypes';

const API_URL = getApiBaseUrl();

export default function MindscapePage() {
  const router = useRouter();
  const [onboardingState, setOnboardingState] = useState<OnboardingState | null>(null);
  const [showSelfIntroDialog, setShowSelfIntroDialog] = useState(false);
  const [showCongrats, setShowCongrats] = useState(false);
  const [currentMode, setCurrentMode] = useState<CurrentMode | null>(null);
  const [suggestions, setSuggestions] = useState<MindscapeSuggestion[]>([]);
  const [profile, setProfile] = useState<MindscapeProfile | null>(null);
  const [intents, setIntents] = useState<MindscapeIntent[]>([]);
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
        loadMindscapeData(),
      ]);
    } catch (err) {
      console.error('Failed to load data:', err);
    } finally {
      setLoading(false);
    }
  };

  const loadOnboardingStatus = async () => {
    try {
      const data = await fetchOnboardingStatus(apiUrl, profileId);
      if (data) {
        console.log('Onboarding status data:', data);
        console.log('onboarding_state keys:', Object.keys(data.onboarding_state || {}));
        setOnboardingState(data.onboarding_state);

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
      try {
        const profileData = await fetchMindscapeProfile(apiUrl, profileId);
        if (profileData) {
          setProfile(profileData);
        }
      } catch (err) {
        console.log('Profile not found, will use defaults');
      }

      try {
        const intentsData = await fetchMindscapeIntents(apiUrl, profileId);
        if (intentsData) {
          setIntents(intentsData);
        }
      } catch (err) {
        console.log('Intents not found');
      }

      try {
        const modeData = await fetchCurrentMode(apiUrl, profileId);
        if (modeData) {
          setCurrentMode(modeData);
        }
      } catch (err) {
        console.log('Failed to load current mode');
        setCurrentMode({
          mainMode: '未設定',
          weeklyFocus: [],
          aiAssistants: [],
        });
      }

      try {
        const suggestionsData = await fetchPendingSuggestions(apiUrl, profileId);
        if (suggestionsData) {
          setSuggestions(suggestionsData);
        }
      } catch (err) {
        console.log('Failed to load suggestions');
      }
    } catch (err) {
      console.error('Failed to load mindscape data:', err);
    }
  };

  const handleCompleteSelfIntro = async (data: SelfIntroPayload) => {
    try {
      await completeSelfIntro(apiUrl, profileId, data);
      await loadAllData();
      alert(t('setupCompleteAlert' as any));
    } catch (err: any) {
      console.error('Failed to complete self intro:', err);
      throw err;
    }
  };

  const handleAcceptSuggestion = async (suggestion: MindscapeSuggestion) => {
    try {
      await reviewSuggestion(apiUrl, suggestion.id, 'accept');
      setSuggestions(suggestions.filter(s => s.id !== suggestion.id));
      alert(`已接受建議：${suggestion.title}`);
      loadMindscapeData();
    } catch (err: any) {
      alert(`接受建議失敗：${err.message}`);
    }
  };

  const handleDismissSuggestion = async (suggestion: MindscapeSuggestion) => {
    try {
      await reviewSuggestion(apiUrl, suggestion.id, 'dismiss');
      setSuggestions(suggestions.filter(s => s.id !== suggestion.id));
    } catch (err: any) {
      alert(`略過建議失敗：${err.message}`);
    }
  };

  const handleStartDailyPlanning = async () => {
    try {
      const workspace = await fetchFirstWorkspace(apiUrl, profileId);
      if (workspace.workspaceId) {
        const intentCreated = await createMindscapeIntent(apiUrl, profileId, DAILY_PLANNING_INTENT_PAYLOAD);
        if (intentCreated) {
          router.push(`/workspaces/${workspace.workspaceId}?playbook=daily_planning`);
        }
      }
    } catch (err) {
      console.error('Failed to start daily planning:', err);
    }
  };

  const handleStartContentDrafting = async () => {
    try {
      const workspace = await fetchFirstWorkspace(apiUrl, profileId);
      if (workspace.workspaceId) {
        const contentType = prompt('這次要寫什麼？（例如：募資頁、IG 貼文、課程介紹）');
        if (contentType) {
          const intentCreated = await createMindscapeIntent(
            apiUrl,
            profileId,
            buildContentDraftingIntentPayload(contentType)
          );
          if (intentCreated) {
            router.push(`/workspaces/${workspace.workspaceId}?playbook=content_drafting`);
          }
        }
      }
    } catch (err) {
      console.error('Failed to start content drafting:', err);
    }
  };

  const handleStartSystemCheck = async () => {
    try {
      const workspace = await fetchFirstWorkspace(apiUrl, profileId);
      if (workspace.workspaceId) {
        router.push(`/workspaces/${workspace.workspaceId}?mode=system_check`);
      }
    } catch (err) {
      console.error('Failed to start system check:', err);
    }
  };

  const handleContinueIntent = async (intent: MindscapeIntent) => {
    try {
      const workspace = await fetchFirstWorkspace(apiUrl, profileId);
      if (workspace.workspaceId) {
        router.push(`/workspaces/${workspace.workspaceId}?intent=${intent.id}`);
      }
    } catch (err) {
      console.error('Failed to continue intent:', err);
    }
  };

  const handleDirectEntry = async () => {
    try {
      const workspace = await fetchFirstWorkspace(apiUrl, profileId);
      if (workspace.ok) {
        if (workspace.workspaceId) {
          router.push(`/workspaces/${workspace.workspaceId}`);
        } else {
          router.push('/workspaces');
        }
      }
    } catch (err) {
      router.push('/workspaces');
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

  console.log('Onboarding state:', onboardingState);
  const isOnboarding = onboardingState?.is_onboarding === true && !onboardingState?.has_state;
  const hasState = onboardingState?.has_state === true;
  console.log('isOnboarding:', isOnboarding, 'hasState:', hasState);

  if (loading) {
    return (
      <div className="min-h-screen bg-gray-50">
        <Header />
        <main className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
          <div className="text-center py-12">
            <p className="text-gray-600">{t('loading' as any)}</p>
          </div>
        </main>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-gray-50">
      <Header />
      <main className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
        <div className="mb-8">
          <h1 className="text-3xl font-bold text-gray-900 mb-2">{t('navMindscape' as any)}</h1>
          <div className="text-gray-600">
            {t('mindscapePageDescription' as any)}
          </div>
        </div>

        {isOnboarding && (
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

        <SelfIntroDialog
          isOpen={showSelfIntroDialog}
          onClose={() => setShowSelfIntroDialog(false)}
          onSubmit={handleCompleteSelfIntro}
        />

        {hasState && !isOnboarding && (
          <div className="mb-8">
            <MindProfileCard profileId={profileId} />
          </div>
        )}

        {hasState && !isOnboarding && (
          <MindscapeEpisodePanel
            intents={intents}
            onStartDailyPlanning={handleStartDailyPlanning}
            onStartContentDrafting={handleStartContentDrafting}
            onStartSystemCheck={handleStartSystemCheck}
            onContinueIntent={handleContinueIntent}
            onDirectEntry={handleDirectEntry}
          />
        )}

        {isOnboarding && (
          <MindscapeOnboardingTasks
            onboardingState={onboardingState}
            profile={profile}
            intents={intents}
            onTask1Click={() => {
              if (onboardingState?.task1_completed) {
                setShowSelfIntroDialog(true);
              } else {
                router.push('/intro');
              }
            }}
            onTask2Click={() => {
              if (onboardingState?.task2_completed) {
                window.location.href = '/playbooks?tags=project';
              } else {
                window.location.href = '/playbooks/project_breakdown_onboarding?onboarding=task2';
              }
            }}
            onTask3Click={() => {
              if (onboardingState?.task3_completed) {
                window.location.href = '/playbooks?tags=planning';
              } else {
                window.location.href = '/playbooks/weekly_review_onboarding?onboarding=task3';
              }
            }}
          />
        )}

        <MindscapeOverviewPanels
          isOnboarding={isOnboarding}
          hasState={hasState}
          currentMode={currentMode}
          suggestions={suggestions}
          profile={profile}
          intents={intents}
          onEditSelfIntro={() => setShowSelfIntroDialog(true)}
          onAcceptSuggestion={handleAcceptSuggestion}
          onDismissSuggestion={handleDismissSuggestion}
        />
      </main>

      <HabitSuggestionToast
        profileId={profileId}
        autoShow={true}
        checkInterval={30000}
      />
    </div>
  );
}
