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
    <div className="bg-white border border-gray-200 rounded-lg p-3 h-full flex flex-col">
      <div className="mb-3">
        <div className="flex items-center justify-between mb-0.5">
          <h3 className="text-xs font-semibold text-gray-900">
            {t('runInsightDraftChanges')}
          </h3>
          {onEditPlaybook && (
            <button
              onClick={onEditPlaybook}
              className="p-1 text-gray-500 hover:text-gray-700 hover:bg-gray-100 rounded transition-colors"
              title={t('editPlaybook')}
            >
              <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M11 5H6a2 2 0 00-2 2v11a2 2 0 002 2h11a2 2 0 002-2v-5m-1.414-9.414a2 2 0 112.828 2.828L11.828 15H9v-2.828l8.586-8.586z" />
              </svg>
            </button>
          )}
        </div>
        <p className="text-[10px] text-gray-500">
          {t('reviewAISuggestions')}
        </p>
      </div>

      {aiSummary && (
        <div className="mb-3 p-2 bg-blue-50 border border-blue-200 rounded-lg">
          <div className="text-[10px] font-semibold text-blue-900 mb-0.5">{t('aiAnalysis')}</div>
          <div className="text-[10px] text-blue-800 whitespace-pre-wrap">{aiSummary}</div>
        </div>
      )}

      <div className="flex-1 overflow-y-auto">
        {revisionPatches.length > 0 ? (
          <div className="space-y-2">
            {revisionPatches.map((patch) => (
              <div
                key={patch.id}
                className="p-2 bg-gray-50 border border-gray-200 rounded hover:border-gray-300 transition-colors"
              >
                <div className="flex items-start justify-between gap-1.5 mb-1">
                  <div className="flex items-center gap-1.5 flex-1">
                    <span className="text-[10px] font-medium text-gray-900">
                      {patch.description}
                    </span>
                  </div>
                  <div className="flex items-center gap-1">
                    {onApplyPatch && (
                      <button
                        onClick={() => onApplyPatch(patch.id)}
                        className="px-1.5 py-0.5 text-[10px] font-medium text-green-700 bg-green-50 border border-green-200 rounded hover:bg-green-100 transition-colors"
                      >
                        {t('apply')}
                      </button>
                    )}
                    {onDiscardPatch && (
                      <button
                        onClick={() => onDiscardPatch(patch.id)}
                        className="px-1.5 py-0.5 text-[10px] font-medium text-gray-600 bg-gray-100 border border-gray-200 rounded hover:bg-gray-200 transition-colors"
                      >
                        {t('discard')}
                      </button>
                    )}
                  </div>
                </div>
                {patch.target_step !== undefined && (
                  <div className="text-[10px] text-gray-500">
                    {t('stepNumber', { number: patch.target_step + 1 })}
                  </div>
                )}
              </div>
            ))}
          </div>
        ) : (
          <div className="flex items-center justify-center h-24 text-[10px] text-gray-400">
            <div className="text-center">
              <p>{t('noRevisionSuggestions')}</p>
              <p className="mt-0.5 text-[10px]">{t('chatWithPlaybookInspector')}</p>
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

