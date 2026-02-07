'use client';

import React, { useState } from 'react';
import { useT } from '@/lib/i18n';

interface PlaybookStep {
  step_index: number;
  step_name: string;
  description?: string;
  agent_type?: string;
  used_tools?: string[];
}

interface RevisionPatch {
  id: string;
  type: 'update' | 'add' | 'remove' | 'merge';
  target_step?: number;
  description: string;
  details?: unknown;
}

interface PlaybookRevisionAreaProps {
  playbookCode?: string;
  playbookSteps?: PlaybookStep[];
  revisionPatches?: RevisionPatch[];
  aiSummary?: string;
  onApplyPatch?: (patchId: string) => void;
  onDiscardPatch?: (patchId: string) => void;
  onEditPlaybook?: () => void;
}

export default function PlaybookRevisionArea({
  playbookCode,
  playbookSteps = [],
  revisionPatches = [],
  aiSummary,
  onApplyPatch,
  onDiscardPatch,
  onEditPlaybook
}: PlaybookRevisionAreaProps) {
  const t = useT();
  const [selectedStepIndex, setSelectedStepIndex] = useState<number | null>(null);

  return (
    <div className="bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-700 rounded-lg p-3 h-full flex flex-col">
      <div className="mb-3">
        <div className="flex items-center justify-between mb-0.5">
          <h3 className="text-xs font-semibold text-gray-900 dark:text-gray-100">
            {t('runInsightDraftChanges' as any)}
          </h3>
          {onEditPlaybook && (
            <button
              onClick={onEditPlaybook}
              className="p-1 text-gray-500 dark:text-gray-400 hover:text-gray-700 dark:hover:text-gray-300 hover:bg-gray-100 dark:hover:bg-gray-700 rounded transition-colors"
              title={t('editPlaybook' as any)}
            >
              <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M11 5H6a2 2 0 00-2 2v11a2 2 0 002 2h11a2 2 0 002-2v-5m-1.414-9.414a2 2 0 112.828 2.828L11.828 15H9v-2.828l8.586-8.586z" />
              </svg>
            </button>
          )}
        </div>
        <p className="text-[10px] text-gray-500 dark:text-gray-300">
          {t('reviewAISuggestions' as any)}
        </p>
      </div>

      {aiSummary && (
        <div className="mb-3 p-2 bg-blue-50 dark:bg-blue-900/20 border border-blue-200 dark:border-blue-700 rounded-lg">
          <div className="text-[10px] font-semibold text-blue-900 dark:text-blue-300 mb-0.5">{t('aiAnalysis' as any)}</div>
          <div className="text-[10px] text-blue-800 dark:text-blue-200 whitespace-pre-wrap">{aiSummary}</div>
        </div>
      )}

      <div className="flex-1 overflow-y-auto">
        {revisionPatches.length > 0 ? (
          <div className="space-y-2">
            {revisionPatches.map((patch) => (
              <div
                key={patch.id}
                className="p-2 bg-gray-50 dark:bg-gray-700 border border-gray-200 dark:border-gray-600 rounded hover:border-gray-300 dark:hover:border-gray-500 transition-colors"
              >
                <div className="flex items-start justify-between gap-1.5 mb-1">
                  <div className="flex items-center gap-1.5 flex-1">
                    <span className="text-[10px] font-medium text-gray-900 dark:text-gray-100">
                      {patch.description}
                    </span>
                  </div>
                  <div className="flex items-center gap-1">
                    {onApplyPatch && (
                      <button
                        onClick={() => onApplyPatch(patch.id)}
                        className="px-1.5 py-0.5 text-[10px] font-medium text-green-700 dark:text-green-300 bg-green-50 dark:bg-green-900/30 border border-green-200 dark:border-green-700 rounded hover:bg-green-100 dark:hover:bg-green-900/40 transition-colors"
                      >
                        {t('apply' as any)}
                      </button>
                    )}
                    {onDiscardPatch && (
                      <button
                        onClick={() => onDiscardPatch(patch.id)}
                        className="px-1.5 py-0.5 text-[10px] font-medium text-gray-600 dark:text-gray-300 bg-gray-100 dark:bg-gray-600 border border-gray-200 dark:border-gray-500 rounded hover:bg-gray-200 dark:hover:bg-gray-500 transition-colors"
                      >
                        {t('discard' as any)}
                      </button>
                    )}
                  </div>
                </div>
                {patch.target_step !== undefined && (
                  <div className="text-[10px] text-gray-500 dark:text-gray-300">
                    {t('stepNumber', { number: String(patch.target_step + 1) })}
                  </div>
                )}
              </div>
            ))}
          </div>
        ) : (
          <div className="flex items-center justify-center h-24 text-[10px] text-gray-400 dark:text-gray-300">
            <div className="text-center">
              <p>{t('noRevisionSuggestions' as any)}</p>
              <p className="mt-0.5 text-[10px]">{t('chatWithPlaybookInspector' as any)}</p>
            </div>
          </div>
        )}
      </div>

      {/*
      <div className="grid grid-cols-2 gap-4 h-full">
        <div className="border-r border-gray-200 pr-4">
          <h4 className="text-xs font-semibold text-gray-900 mb-2">Current Playbook Structure</h4>
          <div className="space-y-1">
            {playbookSteps.map((step) => (
              <div
                key={step.step_index}
                onClick={() => setSelectedStepIndex(step.step_index)}
                className={`p-2 rounded border cursor-pointer text-xs ${
                  selectedStepIndex === step.step_index
                    ? 'border-blue-300 bg-blue-50'
                    : 'border-gray-200 hover:border-gray-300'
                }`}
              >
                <div className="font-medium">Step {step.step_index + 1}: {step.step_name}</div>
                {step.description && (
                  <div className="text-[10px] text-gray-600 mt-0.5">{step.description}</div>
                )}
              </div>
            ))}
          </div>
        </div>
        <div className="pl-4">
          <h4 className="text-xs font-semibold text-gray-900 mb-2">Revision Draft</h4>
          <div className="space-y-2">
            {revisionPatches.map((patch) => (
              <div key={patch.id} className="p-2 bg-yellow-50 border border-yellow-200 rounded text-xs">
                {patch.description}
              </div>
            ))}
          </div>
        </div>
      </div>
      */}
    </div>
  );
}

