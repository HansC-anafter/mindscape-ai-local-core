'use client';

import React from 'react';
import { t } from '@/lib/i18n';

interface ErrorDisplayProps {
  error: string | null;
  onRetry?: () => void;
}

/**
 * ErrorDisplay Component
 * Displays error messages with optional retry functionality.
 *
 * @param error The error message to display.
 * @param onRetry Optional callback function for retry action.
 */
export function ErrorDisplay({ error, onRetry }: ErrorDisplayProps) {
  if (!error) {
    return null;
  }

  return (
    <div className="text-center text-red-500 dark:text-red-400 mt-8 p-4 bg-red-50 dark:bg-red-900/20 rounded-lg">
      <p className="font-semibold">{t('failedToLoadWorkspace')}</p>
      <p className="text-sm mt-2">{error}</p>
      {onRetry && (
        <button
          onClick={onRetry}
          className="mt-2 px-4 py-2 bg-blue-600 text-white rounded hover:bg-blue-700"
        >
          {t('retryButton')}
        </button>
      )}
    </div>
  );
}

