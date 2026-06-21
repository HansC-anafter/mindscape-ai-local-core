import React from 'react';
import TaskCard from '../../components/TaskCard';
import { t } from '../../lib/i18n';
import { formatLocalDateTime } from '@/lib/time';
import type { MindscapeIntent, MindscapeProfile, OnboardingState } from './mindscapePageTypes';

interface MindscapeOnboardingTasksProps {
  onboardingState: OnboardingState | null;
  profile: MindscapeProfile | null;
  intents: MindscapeIntent[];
  onTask1Click: () => void;
  onTask2Click: () => void;
  onTask3Click: () => void;
}

export function MindscapeOnboardingTasks({
  onboardingState,
  profile,
  intents,
  onTask1Click,
  onTask2Click,
  onTask3Click,
}: MindscapeOnboardingTasksProps) {
  return (
    <div className="grid grid-cols-1 md:grid-cols-3 gap-6 mb-8">
      <TaskCard
        taskNumber={1}
        title={t('roleCardTitle' as any)}
        subtitle={t('onboardingTask1Subtitle')}
        isCompleted={onboardingState?.task1_completed || false}
        footerText={t('onboardingTask1Footer')}
        completedContent={
          profile?.self_description ? (
            <div className="text-sm text-gray-700 space-y-2">
              <p>{t('aiWillUseThisPerspective' as any)}</p>
              <ul className="list-disc list-inside space-y-1">
                <li><strong>{t('currentlyDoing' as any)}</strong>{profile.self_description.identity}</li>
                <li><strong>{t('tryingToSolve' as any)}</strong>{profile.self_description.solving}</li>
                <li><strong>{t('thinking' as any)}</strong>{profile.self_description.thinking}</li>
              </ul>
            </div>
          ) : null
        }
        uncompletedContent={
          <ul className="text-sm text-gray-700 space-y-1 list-disc list-inside">
            <li>{t('whatAreYouMainlyDoing' as any)}</li>
            <li>{t('whatDoYouWantToSolve' as any)}</li>
            <li>{t('whatAreYouThinking' as any)}</li>
          </ul>
        }
        buttonText={onboardingState?.task1_completed ? t('editButton' as any) : t('quickSetup' as any)}
        onButtonClick={onTask1Click}
      />

      <TaskCard
        taskNumber={2}
        title={t('firstLongTermTask' as any)}
        subtitle={t('onboardingTask2Subtitle')}
        isCompleted={onboardingState?.task2_completed || false}
        isBlocked={!onboardingState?.task1_completed}
        blockMessage={t('taskBlockMessage' as any)}
        footerText={t('onboardingTask2Footer')}
        completedContent={
          intents.length > 0 ? (
            <div className="text-sm text-gray-700 space-y-2">
              <p className="mb-2">{t('aiWillUpdateProjectStatus' as any)}</p>
              {intents.slice(0, 2).map((intent) => (
                <div key={intent.id} className="flex items-start">
                  <span className="mr-2">📋</span>
                  <div>
                    <p className="font-medium">{intent.title}</p>
                    <p className="text-xs text-gray-500">{t('lastUpdated' as any)}{formatLocalDateTime(intent.updated_at)}</p>
                  </div>
                </div>
              ))}
            </div>
          ) : null
        }
        uncompletedContent={
          <ul className="text-sm text-gray-700 space-y-1 list-disc list-inside">
            <li>{t('tellUsOneThingYouWantToPush' as any)}</li>
            <li>{t('aiWillBreakItDown' as any)}</li>
            <li>{t('autoCreateFirstIntent' as any)}</li>
          </ul>
        }
        buttonText={onboardingState?.task2_completed ? t('onboardingTask2ButtonCompleted') : t('onboardingTask2ButtonUncompleted')}
        onButtonClick={onTask2Click}
      />

      <TaskCard
        taskNumber={3}
        title={t('onboardingTask3Title')}
        subtitle={t('onboardingTask3Subtitle')}
        isCompleted={onboardingState?.task3_completed || false}
        isBlocked={!onboardingState?.task1_completed}
        blockMessage={t('taskBlockMessage' as any)}
        footerText={t('onboardingTask3Footer')}
        completedContent={
          <div className="text-sm text-gray-700 space-y-2">
            <p>{t('aiWillUseThesePreferences' as any)}</p>
            <p><strong>{t('preferredRhythm' as any)}</strong>{t('morningFocusImportantTasks' as any)}</p>
            <p><strong>{t('commonTools' as any)}</strong>{t('toolsWordPressNotion' as any)}</p>
          </div>
        }
        uncompletedContent={
          <div>
            <ul className="text-sm text-gray-700 space-y-1 list-disc list-inside">
              <li>{t('whatThreeThingsThisWeek' as any)}</li>
              <li>{t('whatToolsDoYouUse' as any)}</li>
              <li>{t('whatWorkRhythmDoYouLike' as any)}</li>
            </ul>
            <div className="mt-3 p-2 bg-blue-50 rounded text-xs text-blue-800">
              {t('onboardingTask3WordPressHint')}
            </div>
          </div>
        }
        buttonText={onboardingState?.task3_completed ? t('onboardingTask3ButtonCompleted') : t('onboardingTask3ButtonUncompleted')}
        onButtonClick={onTask3Click}
      />
    </div>
  );
}
