'use client';

import React from 'react';
import { useT } from '@/lib/i18n';

interface ErrorDisplayProps {
  error: string | null;
  onRetry?: () => void;
}

export function ErrorDisplay({ error, onRetry }: ErrorDisplayProps) {
  const t = useT();
  if (!error) {
    return null;
  }

  return (
    <div className="text-center text-red-500 dark:text-red-400 mt-8 p-4 bg-red-50 dark:bg-red-900/20 rounded-lg">
      <p className="font-semibold">{t('failedToLoadWorkspace' as any)}</p>
      <p className="text-sm mt-2">{error}</p>
      {onRetry && (
        <button
          onClick={onRetry}
          className="mt-2 px-4 py-2 bg-blue-600 text-white rounded hover:bg-blue-700"
        >
          {t('retryButton' as any)}
        </button>
      )}
    </div>
  );
}
