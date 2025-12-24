'use client';

import React from 'react';
import { t } from '@/lib/i18n';
import './SuggestionChip.css';

export interface Suggestion {
  id: string;
  title: string;
  description?: string;
  playbookCode?: string;
  executionId?: string;
  runNumber?: number;
  status?: string;
}

interface SuggestionChipProps {
  suggestion: Suggestion;
  isExecuted: boolean;
  onExecute: () => void;
}

export function SuggestionChip({
  suggestion,
  isExecuted,
  onExecute
}: SuggestionChipProps) {
  const tooltipText = isExecuted && suggestion.runNumber
    ? `${t('executedAt') || 'Executed at'} Run #${suggestion.runNumber} · ${suggestion.status || 'completed'}`
    : undefined;

  return (
    <div className={`suggestion-chip ${isExecuted ? 'executed' : ''} bg-gray-100 dark:bg-gray-800 border border-gray-200 dark:border-gray-700 hover:bg-blue-50 dark:hover:bg-blue-900/30 hover:border-blue-300 dark:hover:border-blue-600`}>
      <div className="chip-content">
        <span className="chip-title text-gray-900 dark:text-gray-100">{suggestion.title}</span>
        {suggestion.description && (
          <span className="chip-description text-gray-600 dark:text-gray-400">{suggestion.description}</span>
        )}
      </div>
      <button
        className="chip-action"
        onClick={(e) => {
          e.preventDefault();
          e.stopPropagation();
          console.log('[SuggestionChip] Execute button clicked:', { suggestionId: suggestion.id, title: suggestion.title });
          onExecute();
        }}
        disabled={isExecuted}
        title={tooltipText}
      >
        {isExecuted ? `${t('executed') || 'Executed'}` : t('execute') || 'Execute'}
      </button>
    </div>
  );
}

