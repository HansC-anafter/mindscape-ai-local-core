'use client';

import Link from 'next/link';
import React from 'react';

export interface WorkflowEvidenceDiagnosticsSummary {
  profile?: string | null;
  scope?: string | null;
  selectedLineCount?: number | null;
  totalLineBudget?: number | null;
  totalCandidateCount?: number | null;
  totalDroppedCount?: number | null;
  renderedSectionCount?: number | null;
  budgetUtilizationRatio?: number | null;
}

interface WorkflowEvidenceSummaryProps extends WorkflowEvidenceDiagnosticsSummary {
  label?: string;
  href?: string | null;
  compact?: boolean;
  showOpenLink?: boolean;
  className?: string;
}

type SummaryTone = 'positive' | 'neutral' | 'caution';

function toneClasses(tone: SummaryTone): string {
  if (tone === 'positive') {
    return 'border-green-200 bg-green-50 text-green-900 dark:border-green-900/40 dark:bg-green-950/20 dark:text-green-200';
  }
  if (tone === 'caution') {
    return 'border-amber-200 bg-amber-50 text-amber-900 dark:border-amber-900/40 dark:bg-amber-950/20 dark:text-amber-200';
  }
  return 'border-slate-200 bg-slate-50 text-slate-900 dark:border-slate-700 dark:bg-slate-900/30 dark:text-slate-200';
}

function summarizeDiagnostics(
  diagnostics: WorkflowEvidenceDiagnosticsSummary
): { tone: SummaryTone; title: string; body: string } {
  const selected = diagnostics.selectedLineCount || 0;
  const budget = diagnostics.totalLineBudget || 0;
  const candidates = diagnostics.totalCandidateCount || 0;
  const dropped = diagnostics.totalDroppedCount || 0;
  const renderedSections = diagnostics.renderedSectionCount || 0;
  const utilization = diagnostics.budgetUtilizationRatio || 0;

  if (selected === 0 && candidates === 0) {
    return {
      tone: 'neutral',
      title: 'Sparse packet',
      body: 'No workflow evidence was selected for this meeting packet.',
    };
  }

  if (dropped > 0 && utilization >= 0.85) {
    return {
      tone: 'caution',
      title: 'Tight budget',
      body: `${dropped} candidate lines were trimmed to fit the packet budget.`,
    };
  }

  if (selected > 0 && budget > 0 && utilization < 0.4) {
    return {
      tone: 'neutral',
      title: 'Underused budget',
      body: 'The packet used a small portion of its available line budget.',
    };
  }

  if (renderedSections <= 1) {
    return {
      tone: 'neutral',
      title: 'Narrow packet',
      body: 'The packet was built from a narrow slice of workflow evidence.',
    };
  }

  return {
    tone: 'positive',
    title: 'Balanced packet',
    body: 'Workflow evidence was selected without significant truncation.',
  };
}

export function WorkflowEvidenceSummary({
  label = 'Workflow Evidence',
  href,
  compact = false,
  showOpenLink = false,
  className = '',
  ...diagnostics
}: WorkflowEvidenceSummaryProps) {
  const summary = summarizeDiagnostics(diagnostics);
  const profile = diagnostics.profile || 'general';
  const scope = diagnostics.scope || 'none';
  const selected = diagnostics.selectedLineCount || 0;
  const budget = diagnostics.totalLineBudget || 0;
  const candidates = diagnostics.totalCandidateCount || 0;
  const dropped = diagnostics.totalDroppedCount || 0;
  const renderedSections = diagnostics.renderedSectionCount || 0;
  const utilization = Math.round((diagnostics.budgetUtilizationRatio || 0) * 100);

  return (
    <div className={`rounded-lg border px-3 py-2 ${toneClasses(summary.tone)} ${className}`}>
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="text-[10px] font-medium uppercase tracking-wide opacity-80">
            {label}
          </div>
          <div className="mt-1 text-sm font-semibold">
            {summary.title}
          </div>
          {!compact && (
            <div className="mt-1 text-xs opacity-85">
              {summary.body}
            </div>
          )}
        </div>
        {showOpenLink && href && (
          <Link
            href={href}
            className="inline-flex items-center rounded-md bg-white/70 px-2.5 py-1 text-[11px] font-medium text-current transition-colors hover:bg-white dark:bg-white/10 dark:hover:bg-white/15"
          >
            Open
          </Link>
        )}
      </div>

      <div className="mt-2 text-xs opacity-85">
        {profile} · {scope}
      </div>
      <div className="mt-1 text-xs opacity-75">
        {selected}/{budget} lines · {renderedSections} sections · {utilization}% used
      </div>
      <div className="mt-1 text-xs opacity-75">
        {candidates} candidates · {dropped} dropped
      </div>
    </div>
  );
}
