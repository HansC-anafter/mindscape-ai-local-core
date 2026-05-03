'use client';

import React, { useState } from 'react';

interface ExecutionSummaryBarProps {
  playbookCode?: string;
  revisionPatches?: any[];
  aiSummary?: string;
  outputCount?: number;
  expectedOutputCount?: number;
  onOpenInsights?: () => void;
  onOpenDrafts?: () => void;
  onOpenOutputs?: () => void;
}

export default function ExecutionSummaryBar({
  revisionPatches = [],
  aiSummary,
  outputCount = 0,
  expectedOutputCount = 0,
  onOpenInsights,
  onOpenDrafts,
  onOpenOutputs
}: ExecutionSummaryBarProps) {
  const [expandedSection, setExpandedSection] = useState<string | null>(null);

  const hasInsights = !!aiSummary;
  const hasDrafts = revisionPatches.length > 0;
  const hasOutputs = outputCount > 0;

  return (
    <div className="bg-surface-secondary dark:bg-gray-900 border-b border-default dark:border-gray-700 px-4 py-1.5 flex-shrink-0">
      <div className="flex items-center gap-4 text-xs">
        <button
          onClick={() => {
            setExpandedSection(expandedSection === 'insights' ? null : 'insights');
            onOpenInsights?.();
          }}
          className={`flex items-center gap-1.5 px-2 py-1 rounded transition-colors ${
            hasInsights
              ? 'text-accent dark:text-blue-400 hover:bg-accent-10 dark:hover:bg-blue-900/20'
            : 'text-gray-400 dark:text-gray-500 hover:bg-tertiary dark:hover:bg-gray-800'
          }`}
        >
          <span>Insight</span>
          <span>
            {hasInsights ? 'Execution insights available' : 'No revision suggestions'}
          </span>
        </button>

        {hasDrafts ? (
          <button
            onClick={() => {
              setExpandedSection(expandedSection === 'drafts' ? null : 'drafts');
              onOpenDrafts?.();
            }}
            className="flex items-center gap-1.5 px-2 py-1 rounded bg-yellow-100 dark:bg-yellow-900/30 text-yellow-700 dark:text-yellow-300 hover:bg-yellow-200 dark:hover:bg-yellow-900/40 transition-colors"
          >
            <span>Drafts</span>
            <span className="font-medium">{revisionPatches.length} revision suggestion{revisionPatches.length === 1 ? '' : 's'}</span>
          </button>
        ) : (
          <div className="flex items-center gap-1.5 px-2 py-1 text-gray-400 dark:text-gray-500">
            <span>Drafts</span>
            <span>No revision suggestions</span>
          </div>
        )}

        <button
          onClick={() => {
            setExpandedSection(expandedSection === 'outputs' ? null : 'outputs');
            onOpenOutputs?.();
          }}
          className={`flex items-center gap-1.5 px-2 py-1 rounded transition-colors ${
            hasOutputs
              ? 'text-green-600 dark:text-green-400 hover:bg-accent-10 dark:hover:bg-green-900/20'
            : 'text-gray-400 dark:text-gray-500 hover:bg-tertiary dark:hover:bg-gray-800'
          }`}
        >
          <span>Outputs</span>
          <span>
            Produced: {outputCount}{expectedOutputCount > 0 ? ` / ${expectedOutputCount}` : ''}
          </span>
        </button>
      </div>
    </div>
  );
}
