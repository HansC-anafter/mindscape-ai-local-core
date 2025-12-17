'use client';

import React from 'react';
import ExecutionSummaryBar from '../ExecutionSummaryBar';

export interface SummaryBarProps {
  playbookCode?: string;
  aiSummary?: string;
  outputCount: number;
  onOpenInsights?: () => void;
  onOpenDrafts?: () => void;
  onOpenOutputs?: () => void;
}

export default function SummaryBar({
  playbookCode,
  aiSummary,
  outputCount,
  onOpenInsights,
  onOpenDrafts,
  onOpenOutputs,
}: SummaryBarProps) {
  return (
    <ExecutionSummaryBar
      playbookCode={playbookCode}
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
