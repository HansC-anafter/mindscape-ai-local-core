'use client';

import React from 'react';
import { t } from '@/lib/i18n';

interface OnboardingBannerProps {
  completedCount: number;
  totalCount: number;
  onClose?: () => void;
  showCongrats?: boolean;
  task1Completed: boolean;
  task2Completed: boolean;
  task3Completed: boolean;
}

export default function OnboardingBanner({
  completedCount,
  totalCount,
  onClose,
  showCongrats = false,
  task1Completed,
  task2Completed,
  task3Completed
}: OnboardingBannerProps) {

  // Congrats message when all tasks are complete
  if (showCongrats && completedCount === totalCount) {
    return (
      <div className="bg-gradient-to-r from-green-50 to-emerald-50 border-2 border-green-300 rounded-lg p-6 mb-6 animate-slideDown">
        <div className="flex items-start justify-between">
          <div className="flex-1">
            <div className="flex items-center mb-2">
              <span className="text-3xl mr-3">🎉</span>
              <h2 className="text-xl font-bold text-gray-900">{t('congratulationsFullyActivated')}</h2>
            </div>
            <p className="text-gray-700 ml-12">
              {t('afterTaskCompletion')}
            </p>
          </div>
          {onClose && (
            <button
              onClick={onClose}
              className="ml-4 text-gray-500 hover:text-gray-700 text-2xl"
              aria-label={t('close')}
            >
              ×
            </button>
          )}
        </div>
      </div>
    );
  }

  // Regular onboarding banner with leveled status
  return (
    <div className="bg-gradient-to-r from-gray-50 to-blue-50 border-2 border-gray-200 rounded-lg p-6 mb-6">
      <div className="flex items-start mb-2">
        <span className="text-2xl mr-3">🎯</span>
        <div className="flex-1">
          <h2 className="text-xl font-bold text-gray-900 mb-1">{t('welcomeToMindscape')}</h2>
          {task1Completed ? (
            <p className="text-gray-700 mb-1">{t('mindscapeActivated')}</p>
          ) : (
            <p className="text-gray-700 mb-1">{t('mindscapeNotActivated')}</p>
          )}
          {!task1Completed && (
            <p className="text-sm text-gray-600">{t('optionalCalibration')}</p>
          )}
        </div>
      </div>

      {/* Leveled progress indicator */}
      <div className="ml-11 space-y-2">
        {/* Level 1: Activation Status */}
        <div className="flex items-center space-x-2">
          <span className="text-sm font-medium text-gray-700 w-28">{t('activationStatus')}</span>
          {task1Completed ? (
            <span className="px-3 py-1 bg-green-100 text-green-800 rounded-full text-sm font-medium flex items-center">
              <span className="mr-1">✓</span> {t('activated')}
            </span>
          ) : (
            <span className="px-3 py-1 bg-gray-200 text-gray-600 rounded-full text-sm font-medium">
              {t('notActivated')}
            </span>
          )}
        </div>

        {/* Level 2: Project Calibration */}
        {task1Completed && (
          <div className="flex items-center space-x-2">
            <span className="text-sm font-medium text-gray-700 w-28">{t('projectCalibrationStatus')}</span>
            {task2Completed ? (
              <span className="px-3 py-1 bg-blue-100 text-blue-800 rounded-full text-sm font-medium flex items-center">
                <span className="mr-1">✓</span> {t('activated')}
              </span>
            ) : (
              <span className="px-3 py-1 bg-yellow-100 text-yellow-700 rounded-full text-sm font-medium">
                {t('notActivated')} (選做)
              </span>
            )}
          </div>
        )}

        {/* Level 3: Work Rhythm Calibration */}
        {task1Completed && (
          <div className="flex items-center space-x-2">
            <span className="text-sm font-medium text-gray-700 w-28">{t('workRhythmCalibrationStatus')}</span>
            {task3Completed ? (
              <span className="px-3 py-1 bg-blue-100 text-blue-800 rounded-full text-sm font-medium flex items-center">
                <span className="mr-1">✓</span> {t('activated')}
              </span>
            ) : (
              <span className="px-3 py-1 bg-yellow-100 text-yellow-700 rounded-full text-sm font-medium">
                {t('notActivated')} (選做)
              </span>
            )}
          </div>
        )}

        {task1Completed && (
          <p className="text-sm text-gray-600 mt-2">
            {t('afterCompletionMindscapeWillOrganize')}
          </p>
        )}
      </div>
    </div>
  );
}
