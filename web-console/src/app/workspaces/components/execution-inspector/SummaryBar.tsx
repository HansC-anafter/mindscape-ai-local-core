'use client';

import React from 'react';
import ExecutionSummaryBar from '../ExecutionSummaryBar';
import type { LifecycleSummary } from '../execution-status/lifecycleStatusPresenter';

export interface SummaryBarProps {
  playbookCode?: string;
  executionStatus?: string;
  lifecycleSummary?: LifecycleSummary | null;
  aiSummary?: string;
  outputCount: number;
  onOpenInsights?: () => void;
  onOpenDrafts?: () => void;
  onOpenOutputs?: () => void;
}

export default function SummaryBar({
  playbookCode,
  executionStatus,
  lifecycleSummary,
  aiSummary,
  outputCount,
  onOpenInsights,
  onOpenDrafts,
  onOpenOutputs,
}: SummaryBarProps) {
  return (
    <ExecutionSummaryBar
      playbookCode={playbookCode}
      executionStatus={executionStatus}
      lifecycleSummary={lifecycleSummary}
      revisionPatches={[]}
      aiSummary={aiSummary}
      outputCount={outputCount}
      expectedOutputCount={0}
      onOpenInsights={onOpenInsights}
      onOpenDrafts={onOpenDrafts}
      onOpenOutputs={onOpenOutputs}
    />
  );
}
