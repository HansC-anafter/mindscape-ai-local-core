'use client';

import React, { useState } from 'react';
import { useT } from '@/lib/i18n';

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
  playbookCode,
  revisionPatches = [],
  aiSummary,
  outputCount = 0,
  expectedOutputCount = 0,
  onOpenInsights,
  onOpenDrafts,
  onOpenOutputs
}: ExecutionSummaryBarProps) {
  const t = useT();
  const [expandedSection, setExpandedSection] = useState<string | null>(null);

  const hasInsights = !!aiSummary;
  const hasDrafts = revisionPatches.length > 0;
  const hasOutputs = outputCount > 0;

  return (
    <div className="bg-white dark:bg-gray-900 border-b border-gray-200 dark:border-gray-700 px-4 py-1.5 flex-shrink-0">
      <div className="flex items-center gap-4 text-xs">
        {/* 執行洞察 */}
        <button
          onClick={() => {
            setExpandedSection(expandedSection === 'insights' ? null : 'insights');
            onOpenInsights?.();
          }}
          className={`flex items-center gap-1.5 px-2 py-1 rounded transition-colors ${
            hasInsights
              ? 'text-blue-600 dark:text-blue-400 hover:bg-blue-50 dark:hover:bg-blue-900/20'
              : 'text-gray-400 dark:text-gray-500 hover:bg-gray-50 dark:hover:bg-gray-800'
          }`}
        >
          <span>💡</span>
          <span>
            {hasInsights ? '有執行洞察' : '尚無修正建議'}
          </span>
        </button>

        {/* 修正草案 */}
        {hasDrafts ? (
          <button
            onClick={() => {
              setExpandedSection(expandedSection === 'drafts' ? null : 'drafts');
              onOpenDrafts?.();
            }}
            className="flex items-center gap-1.5 px-2 py-1 rounded bg-yellow-100 dark:bg-yellow-900/30 text-yellow-700 dark:text-yellow-300 hover:bg-yellow-200 dark:hover:bg-yellow-900/40 transition-colors"
          >
            <span>📝</span>
            <span className="font-medium">有 {revisionPatches.length} 則修正建議</span>
          </button>
        ) : (
          <div className="flex items-center gap-1.5 px-2 py-1 text-gray-400 dark:text-gray-500">
            <span>📝</span>
            <span>尚無修正建議</span>
          </div>
        )}

        {/* 已產出 */}
        <button
          onClick={() => {
            setExpandedSection(expandedSection === 'outputs' ? null : 'outputs');
            onOpenOutputs?.();
          }}
          className={`flex items-center gap-1.5 px-2 py-1 rounded transition-colors ${
            hasOutputs
              ? 'text-green-600 dark:text-green-400 hover:bg-green-50 dark:hover:bg-green-900/20'
              : 'text-gray-400 dark:text-gray-500 hover:bg-gray-50 dark:hover:bg-gray-800'
          }`}
        >
          <span>📦</span>
          <span>
            已產出：{outputCount}{expectedOutputCount > 0 ? ` / ${expectedOutputCount}` : ''}
          </span>
        </button>
      </div>
    </div>
  );
}
