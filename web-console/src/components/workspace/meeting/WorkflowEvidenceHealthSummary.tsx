'use client';

import React, { useEffect, useMemo, useState } from 'react';
import { useT } from '@/lib/i18n';

import { subscribeEventStream } from '../eventProjector';

type TranslateFn = (key: any, params?: Record<string, string>) => string;

interface WorkflowEvidenceHealthSession {
  session_id: string;
  project_id?: string | null;
  thread_id?: string | null;
  meeting_type: string;
  started_at: string;
  ended_at?: string | null;
  profile: string;
  scope: string;
  total_candidate_count: number;
  selected_line_count: number;
  total_line_budget: number;
  total_dropped_count: number;
  rendered_section_count: number;
  budget_utilization_ratio: number;
  classification: 'balanced' | 'tight' | 'sparse' | 'underused' | 'narrow' | 'empty';
}

interface WorkflowEvidenceHealthResponse {
  workspace_id: string;
  project_id?: string | null;
  thread_id?: string | null;
  sampled_sessions: number;
  average_utilization_ratio: number;
  average_selected_line_count: number;
  average_total_dropped_count: number;
  balanced_count: number;
  tight_count: number;
  sparse_count: number;
  underused_count: number;
  narrow_count: number;
  empty_count: number;
  latest?: WorkflowEvidenceHealthSession | null;
  sessions: WorkflowEvidenceHealthSession[];
}

interface WorkflowEvidenceHealthSummaryProps {
  workspaceId: string;
  apiUrl: string;
  selectedThreadId?: string | null;
  limit?: number;
  showRecentSessions?: boolean;
  className?: string;
}

function toneClassFromHealth(response: WorkflowEvidenceHealthResponse | null): string {
  if (!response || response.sampled_sessions === 0) {
    return 'border-slate-200 bg-slate-50 text-slate-900 dark:border-slate-700 dark:bg-slate-900/30 dark:text-slate-200';
  }
  if (response.tight_count > 0) {
    return 'border-amber-200 bg-amber-50 text-amber-900 dark:border-amber-900/40 dark:bg-amber-950/20 dark:text-amber-200';
  }
  if (response.empty_count === response.sampled_sessions) {
    return 'border-slate-200 bg-slate-50 text-slate-900 dark:border-slate-700 dark:bg-slate-900/30 dark:text-slate-200';
  }
  return 'border-green-200 bg-green-50 text-green-900 dark:border-green-900/40 dark:bg-green-950/20 dark:text-green-200';
}

function titleFromHealth(response: WorkflowEvidenceHealthResponse | null, t: TranslateFn): string {
  if (!response || response.sampled_sessions === 0) {
    return t('noPacketHistory' as any);
  }
  if (response.tight_count > 0) {
    return t('recentTruncationDetected' as any);
  }
  if (response.empty_count === response.sampled_sessions) {
    return t('sparsePacketHistory' as any);
  }
  return t('stablePacketHistory' as any);
}

function classificationLabel(
  classification: WorkflowEvidenceHealthSession['classification'],
  t: TranslateFn
): string {
  if (classification === 'balanced') {
    return t('balanced' as any);
  }
  if (classification === 'tight') {
    return t('tight' as any);
  }
  if (classification === 'sparse') {
    return t('sparse' as any);
  }
  if (classification === 'underused') {
    return t('underused' as any);
  }
  if (classification === 'narrow') {
    return t('narrow' as any);
  }
  if (classification === 'empty') {
    return t('empty' as any);
  }
  return classification.replace(/_/g, ' ');
}

function classificationBadgeClass(
  classification: WorkflowEvidenceHealthSession['classification']
): string {
  if (classification === 'balanced') {
    return 'bg-green-100 text-green-800 dark:bg-green-900/30 dark:text-green-300';
  }
  if (classification === 'tight') {
    return 'bg-amber-100 text-amber-800 dark:bg-amber-900/30 dark:text-amber-300';
  }
  if (classification === 'sparse' || classification === 'empty') {
    return 'bg-slate-200 text-slate-800 dark:bg-slate-800 dark:text-slate-300';
  }
  if (classification === 'underused') {
    return 'bg-blue-100 text-blue-800 dark:bg-blue-900/30 dark:text-blue-300';
  }
  return 'bg-purple-100 text-purple-800 dark:bg-purple-900/30 dark:text-purple-300';
}

function countLabel(count: number, label: string, t: TranslateFn): string {
  return t('workflowHealthCountLabel' as any, {
    count: String(count),
    label,
  });
}

export function WorkflowEvidenceHealthSummary({
  workspaceId,
  apiUrl,
  selectedThreadId,
  limit = 5,
  showRecentSessions = false,
  className = '',
}: WorkflowEvidenceHealthSummaryProps) {
  const t = useT();
  const [summary, setSummary] = useState<WorkflowEvidenceHealthResponse | null>(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    let cancelled = false;

    const load = async () => {
      try {
        setLoading(true);
        const params = new URLSearchParams();
        params.set('limit', String(limit));
        if (selectedThreadId) {
          params.set('thread_id', selectedThreadId);
        }
        const response = await fetch(
          `${apiUrl}/api/v1/workspaces/${workspaceId}/governance/memory-health?${params.toString()}`
        );
        if (!response.ok) {
          throw new Error(`Failed to load workflow evidence health: ${response.status}`);
        }
        const data: WorkflowEvidenceHealthResponse = await response.json();
        if (!cancelled) {
          setSummary(data);
        }
      } catch (err) {
        console.error('Failed to load workflow evidence health:', err);
        if (!cancelled) {
          setSummary(null);
        }
      } finally {
        if (!cancelled) {
          setLoading(false);
        }
      }
    };

    void load();

    const unsubscribe = subscribeEventStream(workspaceId, {
      apiUrl,
      eventTypes: ['meeting_start'],
      onEvent: (event) => {
        if (selectedThreadId && event.thread_id !== selectedThreadId) {
          return;
        }
        void load();
      },
      onError: (error) => {
        console.error('Workflow evidence health stream error:', error);
      },
    });

    return () => {
      cancelled = true;
      unsubscribe();
    };
  }, [apiUrl, limit, selectedThreadId, workspaceId]);

  const latest = summary?.latest || null;
  const title = useMemo(() => titleFromHealth(summary, t), [summary, t]);
  const toneClass = useMemo(() => toneClassFromHealth(summary), [summary]);
  const summaryBreakdown = useMemo(() => {
    if (!summary || summary.sampled_sessions === 0) {
      return [];
    }
    return [
      countLabel(summary.balanced_count, t('balanced' as any), t),
      countLabel(summary.tight_count, t('tight' as any), t),
      countLabel(summary.sparse_count + summary.empty_count, t('sparse' as any), t),
    ];
  }, [summary, t]);
  const recentSessions = showRecentSessions ? summary?.sessions || [] : [];

  return (
    <div className={`rounded-lg border px-3 py-2 ${toneClass} ${className}`}>
      <div className="text-[10px] font-medium uppercase tracking-wide opacity-80">
        {t('workflowEvidenceHealth' as any)}
      </div>
      <div className="mt-1 text-sm font-semibold">
        {loading && !summary ? t('loadingHealthSummary' as any) : title}
      </div>
      <div className="mt-1 text-xs opacity-80">
        {t('workflowHealthScopeSummary' as any, {
          scope: selectedThreadId ? t('threadScope' as any) : t('workspaceScope' as any),
          count: String(summary?.sampled_sessions || 0),
        })}
      </div>
      {summary && summary.sampled_sessions > 0 && (
        <>
          <div className="mt-2 flex flex-wrap gap-1.5 text-[11px]">
            {summaryBreakdown.map((item) => (
              <span
                key={item}
                className="rounded-full bg-white/70 px-2 py-0.5 dark:bg-white/10"
              >
                {item}
              </span>
            ))}
          </div>
          <div className="mt-1 text-xs opacity-75">
            {t('workflowHealthTightSparseUsed' as any, {
              tight: String(summary.tight_count),
              sparse: String(summary.sparse_count + summary.empty_count),
              used: String(Math.round(summary.average_utilization_ratio * 100)),
            })}
          </div>
          <div className="mt-1 text-xs opacity-75">
            {t('workflowHealthSelectedDropped' as any, {
              selected: String(summary.average_selected_line_count),
              dropped: String(summary.average_total_dropped_count),
            })}
          </div>
          {latest && (
            <div className="mt-2 text-xs opacity-75">
              {t('workflowHealthLatestSession' as any, {
                profile: latest.profile,
                scope: latest.scope,
                selected: String(latest.selected_line_count),
                budget: String(latest.total_line_budget),
              })}
            </div>
          )}
          {recentSessions.length > 0 && (
            <div className="mt-3 space-y-2">
              {recentSessions.map((session) => (
                <div
                  key={session.session_id}
                  className="rounded-md border border-white/60 bg-white/70 px-2.5 py-2 text-xs dark:border-white/10 dark:bg-white/5"
                >
                  <div className="flex items-center justify-between gap-2">
                    <div className="font-medium text-current">
                      {session.profile} · {session.scope}
                    </div>
                    <span
                      className={`rounded-full px-2 py-0.5 text-[10px] font-medium uppercase tracking-wide ${classificationBadgeClass(
                        session.classification
                      )}`}
                    >
                      {classificationLabel(session.classification, t)}
                    </span>
                  </div>
                  <div className="mt-1 opacity-75">
                    {t('workflowHealthSessionSummary' as any, {
                      selected: String(session.selected_line_count),
                      budget: String(session.total_line_budget),
                      dropped: String(session.total_dropped_count),
                      sections: String(session.rendered_section_count),
                    })}
                  </div>
                </div>
              ))}
            </div>
          )}
        </>
      )}
    </div>
  );
}
