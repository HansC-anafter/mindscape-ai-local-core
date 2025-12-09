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
    <div className={`suggestion-chip ${isExecuted ? 'executed' : ''}`}>
      <div className="chip-content">
        <span className="chip-title">{suggestion.title}</span>
        {suggestion.description && (
          <span className="chip-description">{suggestion.description}</span>
        )}
      </div>
      <button
        className="chip-action"
        onClick={onExecute}
        disabled={isExecuted}
        title={tooltipText}
      >
        {isExecuted ? `${t('executed') || 'Executed'}` : t('execute') || 'Execute'}
      </button>
    </div>
  );
}

