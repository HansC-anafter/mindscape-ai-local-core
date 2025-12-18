'use client';

import React from 'react';
import { t } from '@/lib/i18n';

interface LLMNotConfiguredOverlayProps {
  visible: boolean;
}

/**
 * LLMNotConfiguredOverlay Component
 * Displays an overlay when LLM is not configured.
 *
 * @param visible Whether the overlay should be visible.
 */
export function LLMNotConfiguredOverlay({ visible }: LLMNotConfiguredOverlayProps) {
  if (!visible) {
    return null;
  }

  return (
    <div className="absolute inset-0 bg-white/95 dark:bg-gray-900/95 backdrop-blur-sm z-50 flex items-center justify-center">
      <div className="max-w-md mx-4 p-6 bg-white dark:bg-gray-800 rounded-lg shadow-lg border-2 border-yellow-300 dark:border-yellow-600">
        <div className="flex items-start space-x-4">
          <div className="flex-shrink-0">
            <svg className="w-8 h-8 text-yellow-500" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
            </svg>
          </div>
          <div className="flex-1">
            <h3 className="text-lg font-semibold text-gray-900 dark:text-gray-100 mb-2">
              {t('apiKeyNotConfigured')}
            </h3>
            <p className="text-sm text-gray-600 dark:text-gray-400 mb-4">
              {t('apiKeyNotConfiguredDescription')}
            </p>
            <a
              href="/settings"
              className="text-sm text-blue-600 hover:text-blue-800 underline"
            >
              {t('goToSettings')} →
            </a>
          </div>
        </div>
      </div>
    </div>
  );
}

