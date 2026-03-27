'use client';

import Link from 'next/link';
import React, { useEffect, useMemo, useState } from 'react';

interface EvidenceCoverageSummary {
  deliberation: number;
  execution: number;
  governance: number;
  support: number;
  derived: number;
}

interface TransitionCueSummary {
  id: string;
  tone: 'positive' | 'neutral' | 'caution';
  title: string;
  body: string;
}

interface ArtifactLandingDrilldownSummary {
  attachments_count: number;
  artifact_dir_exists: boolean;
  result_json_exists: boolean;
  summary_md_exists: boolean;
}

interface ExecutionTraceDrilldownSummary {
  trace_source?: string | null;
  trace_file_exists: boolean;
  output_summary?: string | null;
}

interface MemoryEvidencePreviewSummary {
  evidence_type: string;
  artifact_landing?: ArtifactLandingDrilldownSummary | null;
  execution_trace_drilldown?: ExecutionTraceDrilldownSummary | null;
}

interface WorkspaceMemoryDetailPayload {
  memory_item: {
    id: string;
    title: string;
    summary: string;
    claim: string;
    lifecycle_status: string;
    verification_status: string;
  };
  evidence_coverage?: EvidenceCoverageSummary;
  transition_cues?: TransitionCueSummary[];
  evidence?: MemoryEvidencePreviewSummary[];
}

interface GovernedMemoryPreviewProps {
  workspaceId: string;
  memoryItemId: string;
  apiUrl: string;
  lifecycleStatus?: string;
  verificationStatus?: string;
  href?: string | null;
  compact?: boolean;
  showOpenLink?: boolean;
  className?: string;
}

const governedMemoryPreviewCache = new Map<string, WorkspaceMemoryDetailPayload>();

function badgeClass(status?: string): string {
  if (status === 'active' || status === 'verified') {
    return 'bg-green-100 text-green-800 dark:bg-green-900/30 dark:text-green-300';
  }
  if (status === 'candidate' || status === 'observed') {
    return 'bg-amber-100 text-amber-800 dark:bg-amber-900/30 dark:text-amber-300';
  }
  if (status === 'stale' || status === 'challenged') {
    return 'bg-slate-100 text-slate-800 dark:bg-slate-800 dark:text-slate-300';
  }
  if (status === 'superseded' || status === 'deprecated') {
    return 'bg-purple-100 text-purple-800 dark:bg-purple-900/30 dark:text-purple-300';
  }
  return 'bg-gray-100 text-gray-700 dark:bg-gray-800 dark:text-gray-300';
}

function cueToneClass(tone: TransitionCueSummary['tone']): string {
  if (tone === 'positive') {
    return 'border-green-200 bg-green-50 text-green-900 dark:border-green-900/50 dark:bg-green-900/20 dark:text-green-200';
  }
  if (tone === 'caution') {
    return 'border-amber-200 bg-amber-50 text-amber-900 dark:border-amber-900/50 dark:bg-amber-900/20 dark:text-amber-200';
  }
  return 'border-slate-200 bg-slate-50 text-slate-900 dark:border-slate-700 dark:bg-slate-900/30 dark:text-slate-200';
}

export function GovernedMemoryPreview({
  workspaceId,
  memoryItemId,
  apiUrl,
  lifecycleStatus,
  verificationStatus,
  href,
  compact = false,
  showOpenLink = true,
  className = '',
}: GovernedMemoryPreviewProps) {
  const [detail, setDetail] = useState<WorkspaceMemoryDetailPayload | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!workspaceId || !memoryItemId) {
      setDetail(null);
      setError(null);
      setLoading(false);
      return;
    }

    const cacheKey = `${workspaceId}:${memoryItemId}`;
    const cached = governedMemoryPreviewCache.get(cacheKey);
    if (cached) {
      setDetail(cached);
      setError(null);
      setLoading(false);
      return;
    }

    let cancelled = false;

    const load = async () => {
      try {
        setLoading(true);
        setError(null);
        const response = await fetch(
          `${apiUrl}/api/v1/workspaces/${workspaceId}/governance/memory/${memoryItemId}`
        );
        if (!response.ok) {
          throw new Error(`Failed to load governed memory detail: ${response.status}`);
        }
        const data: WorkspaceMemoryDetailPayload = await response.json();
        if (!cancelled) {
          governedMemoryPreviewCache.set(cacheKey, data);
          setDetail(data);
        }
      } catch (err) {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : 'Failed to load governed memory detail');
        }
      } finally {
        if (!cancelled) {
          setLoading(false);
        }
      }
    };

    void load();

    return () => {
      cancelled = true;
    };
  }, [apiUrl, memoryItemId, workspaceId]);

  const resolvedHref = useMemo(() => {
    if (href) {
      return href;
    }
    const params = new URLSearchParams();
    params.set('tab', 'memory');
    params.set('memoryId', memoryItemId);
    return `/workspaces/${workspaceId}/governance?${params.toString()}`;
  }, [href, memoryItemId, workspaceId]);

  const item = detail?.memory_item;
  const coverage = detail?.evidence_coverage;
  const cue = detail?.transition_cues?.[0] || null;
  const summary = item?.summary || item?.claim || '';
  const artifactLanding =
    detail?.evidence?.find((entry) => entry.evidence_type === 'artifact_result')?.artifact_landing || null;
  const traceDrilldown =
    detail?.evidence?.find((entry) => entry.evidence_type === 'execution_trace')
      ?.execution_trace_drilldown || null;
  const effectiveLifecycle = item?.lifecycle_status || lifecycleStatus;
  const effectiveVerification = item?.verification_status || verificationStatus;

  return (
    <div className={`rounded-lg border border-sky-200 bg-sky-50/70 p-3 dark:border-sky-800 dark:bg-sky-950/30 ${className}`}>
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="text-[10px] font-medium uppercase tracking-wide text-sky-700 dark:text-sky-300">
            Governed Memory
          </div>
          <div className="mt-1 text-sm font-semibold text-sky-900 dark:text-sky-100 break-words">
            {item?.title || memoryItemId}
          </div>
          <div className="mt-2 flex flex-wrap gap-2">
            {effectiveLifecycle && (
              <span className={`rounded px-2 py-1 text-[11px] font-medium ${badgeClass(effectiveLifecycle)}`}>
                {effectiveLifecycle}
              </span>
            )}
            {effectiveVerification && (
              <span className={`rounded px-2 py-1 text-[11px] font-medium ${badgeClass(effectiveVerification)}`}>
                {effectiveVerification}
              </span>
            )}
          </div>
        </div>
        {showOpenLink && resolvedHref && (
          <Link
            href={resolvedHref}
            className="inline-flex items-center rounded-md bg-sky-600 px-3 py-1.5 text-xs font-medium text-white transition-colors hover:bg-sky-700"
          >
            Open
          </Link>
        )}
      </div>

      <div className="mt-2 text-xs font-mono break-all text-sky-700/90 dark:text-sky-300/90">
        {memoryItemId}
      </div>

      {loading ? (
        <div className="mt-3 text-sm text-sky-800 dark:text-sky-100">Loading governed memory detail...</div>
      ) : error ? (
        <div className="mt-3 text-sm text-amber-800 dark:text-amber-200">{error}</div>
      ) : (
        <>
          {summary && (
            <div className={`mt-3 text-sm text-sky-900 dark:text-sky-100 ${compact ? 'line-clamp-2' : ''}`}>
              {summary}
            </div>
          )}

          {coverage && (
            <div className="mt-3 grid grid-cols-2 gap-2 xl:grid-cols-4">
              <div className="rounded border border-sky-200/80 bg-white/70 px-2.5 py-2 dark:border-sky-900/50 dark:bg-sky-950/40">
                <div className="text-[10px] uppercase tracking-wide text-sky-700/80 dark:text-sky-300/80">Deliberation</div>
                <div className="mt-1 text-sm font-semibold text-sky-900 dark:text-sky-100">{coverage.deliberation}</div>
              </div>
              <div className="rounded border border-sky-200/80 bg-white/70 px-2.5 py-2 dark:border-sky-900/50 dark:bg-sky-950/40">
                <div className="text-[10px] uppercase tracking-wide text-sky-700/80 dark:text-sky-300/80">Execution</div>
                <div className="mt-1 text-sm font-semibold text-sky-900 dark:text-sky-100">{coverage.execution}</div>
              </div>
              <div className="rounded border border-sky-200/80 bg-white/70 px-2.5 py-2 dark:border-sky-900/50 dark:bg-sky-950/40">
                <div className="text-[10px] uppercase tracking-wide text-sky-700/80 dark:text-sky-300/80">Governance</div>
                <div className="mt-1 text-sm font-semibold text-sky-900 dark:text-sky-100">{coverage.governance}</div>
              </div>
              <div className="rounded border border-sky-200/80 bg-white/70 px-2.5 py-2 dark:border-sky-900/50 dark:bg-sky-950/40">
                <div className="text-[10px] uppercase tracking-wide text-sky-700/80 dark:text-sky-300/80">Support</div>
                <div className="mt-1 text-sm font-semibold text-sky-900 dark:text-sky-100">{coverage.support}</div>
              </div>
            </div>
          )}

          {cue && (
            <div className={`mt-3 rounded border px-3 py-2 ${cueToneClass(cue.tone)}`}>
              <div className="text-sm font-medium">{cue.title}</div>
              <div className={`mt-1 text-xs leading-5 opacity-90 ${compact ? 'line-clamp-2' : ''}`}>
                {cue.body}
              </div>
            </div>
          )}

          {(artifactLanding || traceDrilldown) && (
            <div className="mt-3 flex flex-wrap gap-2">
              {artifactLanding && (
                <span className="rounded bg-white/70 px-2.5 py-1 text-[11px] text-sky-900 dark:bg-sky-950/40 dark:text-sky-100">
                  Landing {artifactLanding.attachments_count} attachments ·{' '}
                  {artifactLanding.result_json_exists ? 'result ready' : 'result missing'}
                </span>
              )}
              {traceDrilldown && (
                <span className="rounded bg-white/70 px-2.5 py-1 text-[11px] text-sky-900 dark:bg-sky-950/40 dark:text-sky-100">
                  Trace {traceDrilldown.trace_file_exists ? 'file linked' : traceDrilldown.trace_source || 'summary only'}
                </span>
              )}
            </div>
          )}
        </>
      )}
    </div>
  );
}
