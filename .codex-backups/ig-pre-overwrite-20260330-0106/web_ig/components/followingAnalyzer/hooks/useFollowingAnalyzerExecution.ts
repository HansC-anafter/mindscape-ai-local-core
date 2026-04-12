import { useCallback, useEffect, useRef, useState } from 'react';

import { useExecutionPolling } from '@/hooks/useExecutionPolling';
import { toTimestampMs, parseServerTimestamp } from '@/lib/time';

import type { AnalysisResult, AnalyzerProgress } from '../types';

type FollowingExecutionSnapshot = {
  execution_id?: string;
  status?: string;
  failure_reason?: string | null;
  task?: {
    status?: string;
    error?: string | null;
    execution_context?: {
      inputs?: {
        target_username?: string;
        user_data_dir?: string;
        run_mode?: string;
        visit_account_pages?: boolean;
      };
      status?: string;
    };
  };
  execution_context?: {
    inputs?: {
      target_username?: string;
      user_data_dir?: string;
      run_mode?: string;
      visit_account_pages?: boolean;
    };
    status?: string;
  };
  created_at?: string;
  started_at?: string;
  completed_at?: string;
};

type FollowingProgressSnapshot = {
  execution_id?: string;
  task_status?: string;
  artifact_updated_at?: string | null;
  progress?: Record<string, any> | null;
  artifact_metadata?: Record<string, any> | null;
  content_metadata?: Record<string, any> | null;
  execution_context?: {
    inputs?: {
      target_username?: string;
      user_data_dir?: string;
      run_mode?: string;
      visit_account_pages?: boolean;
    };
    status?: string;
  } | null;
};

const REQUEST_TIMEOUT_MS = 15_000;
const START_REQUEST_TIMEOUT_MS = 45_000;
const RECOVERY_LOOKUP_TIMEOUT_MS = 20_000;
const RECOVERY_RETRY_DELAYS_MS = [0, 1_500, 3_000, 5_000, 8_000, 12_000] as const;

async function fetchWithTimeout(
  input: RequestInfo | URL,
  init: RequestInit = {},
  timeoutMs: number = REQUEST_TIMEOUT_MS
): Promise<Response> {
  const controller = new AbortController();
  const timeoutId = window.setTimeout(() => controller.abort(), timeoutMs);

  try {
    return await fetch(input, {
      ...init,
      signal: controller.signal,
    });
  } finally {
    window.clearTimeout(timeoutId);
  }
}

function isAbortError(error: unknown): boolean {
  return error instanceof DOMException && error.name === 'AbortError';
}

function wait(ms: number): Promise<void> {
  return new Promise((resolve) => {
    window.setTimeout(resolve, ms);
  });
}

function parseArtifactContent(artifact: any): any | null {
  try {
    const raw = artifact?.content ?? artifact?.content_preview;
    if (!raw) return null;
    if (typeof raw === 'string') {
      return JSON.parse(raw);
    }
    if (typeof raw === 'object') return raw;
    return null;
  } catch {
    return null;
  }
}

function extractUsername(input: string): string | null {
  const trimmed = input.trim();
  if (!trimmed) return null;

  try {
    const url = new URL(trimmed.startsWith('http') ? trimmed : `https://${trimmed}`);
    const hostname = url.hostname.toLowerCase();

    if (hostname === 'instagram.com' || hostname === 'www.instagram.com') {
      const pathParts = url.pathname.split('/').filter((p) => p);
      if (pathParts.length > 0) {
        return pathParts[0];
      }
    }
  } catch {
    // ignore
  }

  let username = trimmed;

  if (username.startsWith('@')) {
    username = username.slice(1);
  }

  if (username.includes('/')) {
    const parts = username.split('/').filter((p) => p);
    if (parts.length > 0) {
      username = parts[parts.length - 1];
    }
  }

  if (username.includes('?')) {
    username = username.split('?')[0];
  }

  if (username.includes('#')) {
    username = username.split('#')[0];
  }

  return username || null;
}

function normalizeUsername(value: string | null | undefined): string {
  return (value || '').trim().toLowerCase().replace(/^@/, '');
}

function executionInputs(snapshot: FollowingExecutionSnapshot | null | undefined) {
  return snapshot?.task?.execution_context?.inputs || snapshot?.execution_context?.inputs || {};
}

function executionStatus(snapshot: FollowingExecutionSnapshot | null | undefined): string {
  return (
    snapshot?.status ||
    snapshot?.task?.status ||
    snapshot?.task?.execution_context?.status ||
    snapshot?.execution_context?.status ||
    ''
  )
    .toString()
    .trim()
    .toLowerCase();
}

function executionSortTime(snapshot: FollowingExecutionSnapshot): number {
  const value = snapshot.started_at || snapshot.created_at || snapshot.completed_at || 0;
  const parsed = parseServerTimestamp(value) ?? new Date(value);
  const ts = parsed.getTime();
  return Number.isFinite(ts) ? ts : 0;
}

function executionPriority(status: string): number {
  if (status === 'running') return 3;
  if (status === 'pending' || status === 'queued' || status === 'paused') return 2;
  if (status === 'completed' || status === 'succeeded') return 1;
  if (status === 'failed' || status === 'error') return 0;
  return -1;
}

function toFiniteNumber(value: unknown): number | null {
  if (typeof value === 'number' && Number.isFinite(value)) return value;
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : null;
}

function mergeFollowingProgressSnapshot(
  snapshot: FollowingProgressSnapshot,
  previous: AnalyzerProgress | null
): AnalyzerProgress | null {
  const progressRaw = snapshot?.progress;
  const progress = (progressRaw && typeof progressRaw === 'object') ? progressRaw : {};
  const artifactMetaRaw = snapshot?.artifact_metadata;
  const artifactMeta = (artifactMetaRaw && typeof artifactMetaRaw === 'object') ? artifactMetaRaw : {};
  const contentMetaRaw = snapshot?.content_metadata;
  const contentMeta = (contentMetaRaw && typeof contentMetaRaw === 'object') ? contentMetaRaw : {};
  const taskStatus = (snapshot?.task_status || snapshot?.execution_context?.status || '').toString().trim().toLowerCase();

  const stage = (progress.stage || contentMeta.stage || artifactMeta.stage || previous?.stage || '').toString().trim();
  const currentAccount = typeof progress.current_account === 'string'
    ? progress.current_account
    : previous?.currentAccount;
  const pageIndex = toFiniteNumber(progress.page_index);
  const pageTotal = toFiniteNumber(progress.page_total);
  const totalAccounts = toFiniteNumber(progress.total_accounts);
  const countAfter = toFiniteNumber(progress.count_after);
  const saved = toFiniteNumber(progress.saved);

  let current = previous?.current || 0;
  let total = previous?.total || 0;

  if (pageIndex !== null) {
    current = pageIndex;
  } else if (countAfter !== null) {
    current = countAfter;
  } else if (saved !== null) {
    current = saved;
  }

  if (pageTotal !== null) {
    total = pageTotal;
  } else if (totalAccounts !== null) {
    total = totalAccounts;
  }

  let status = previous?.status || 'started';
  if (taskStatus === 'pending' || taskStatus === 'queued' || taskStatus === 'paused') {
    status = 'pending';
  } else if (taskStatus === 'running') {
    status = 'processing';
  } else if (taskStatus === 'completed' || taskStatus === 'succeeded') {
    status = 'completed';
  } else if (taskStatus === 'failed' || taskStatus === 'error' || taskStatus === 'cancelled' || taskStatus === 'cancelled_by_user') {
    status = 'failed';
  } else if (stage) {
    status = stage === 'completed' ? 'completed' : stage === 'error' ? 'failed' : 'processing';
  }

  if (!status && !stage && current === 0 && total === 0) {
    return null;
  }

  return {
    current,
    total,
    status,
    currentAccount,
    stage: stage || previous?.stage,
    updatedAt: snapshot?.artifact_updated_at || previous?.updatedAt,
    pageIndex: pageIndex === null ? previous?.pageIndex : pageIndex,
    pageTotal: pageTotal === null ? previous?.pageTotal : pageTotal,
    secondsPerPage: previous?.secondsPerPage,
    etaSeconds: previous?.etaSeconds,
  };
}

export function useFollowingAnalyzerExecution(params: {
  workspaceId: string;
  baseApiUrl: string;
  onComplete?: (result: AnalysisResult) => void;
  targetUsername: string;
  executionBackend: 'auto' | 'runner';
  visitAccountPages: boolean;
  maxAccounts: number | null;
  resolvedUserDataDir: string;
  runMode?: string;
  allowPartialResume?: boolean;
}) {
  const {
    workspaceId,
    baseApiUrl,
    onComplete,
    targetUsername,
    visitAccountPages,
    maxAccounts,
    resolvedUserDataDir,
    runMode = 'full',
    allowPartialResume = false,
  } = params;

  const [isExecuting, setIsExecuting] = useState(false);
  const [executionId, setExecutionId] = useState<string | null>(null);
  const [progress, setProgress] = useState<AnalyzerProgress | null>(null);
  const [result, setResult] = useState<AnalysisResult | null>(null);
  const [error, setError] = useState<string | null>(null);

  const completionNotifiedRef = useRef(false);
  const visitingPerfRef = useRef<{
    lastAtMs: number | null;
    lastIndex: number | null;
    avgSecondsPerPage: number | null;
  }>({ lastAtMs: null, lastIndex: null, avgSecondsPerPage: null });

  const announceExecutionStarted = useCallback((execId: string) => {
    if (!execId || typeof window === 'undefined') return;
    try {
      window.dispatchEvent(
        new CustomEvent('mindscape:execution_started', {
          detail: {
            workspaceId,
            executionId: execId,
            playbookCode: 'ig_analyze_following',
            startedAt: new Date().toISOString(),
          },
        })
      );
    } catch {
      // ignore
    }
  }, [workspaceId]);

  const fetchResultFromArtifacts = useCallback(async (execId: string) => {
    try {
      // Fallback to artifacts API
      const response = await fetchWithTimeout(
        `${baseApiUrl}/api/v1/workspaces/${workspaceId}/artifacts?playbook_code=ig_analyze_following&limit=200&include_content=false&include_preview=false`,
        { headers: { 'Content-Type': 'application/json' } }
      );

      if (!response.ok) return;

      const data = await response.json();
      const artifacts = data.artifacts || data || [];

      let matchingArtifact = artifacts.find((a: any) =>
        (a.metadata && (a.metadata.execution_id === execId || a.metadata.trace_id === execId)) ||
        (a.artifact_type === 'ig_analyze_following' || a.type === 'ig_analyze_following')
      );

      if (!matchingArtifact && artifacts.length > 0) {
        const recentArtifacts = artifacts.filter((a: any) =>
          a.artifact_type === 'ig_analyze_following' ||
          a.type === 'ig_analyze_following' ||
          a.platform === 'instagram'
        );
        if (recentArtifacts.length > 0) {
          matchingArtifact = recentArtifacts[0];
        }
      }

      if (!matchingArtifact) return;

      let content = parseArtifactContent(matchingArtifact);
      if (!content && matchingArtifact.id) {
        try {
          const single = await fetchWithTimeout(`${baseApiUrl}/api/v1/artifacts/${matchingArtifact.id}?include_content=true&include_preview=false`, {
            headers: { 'Content-Type': 'application/json' },
          });
          if (single.ok) {
            const singleData = await single.json();
            content = parseArtifactContent(singleData);
          }
        } catch {
          // ignore
        }
      }
      if (!content) return;

      if (content && (content.accounts || content.discovered_accounts)) {
        const accounts = content.accounts || content.discovered_accounts || [];
        const summary = content.summary || {
          total_accounts: accounts.length,
          verified_accounts: accounts.filter((a: any) => a.is_verified).length,
          accounts_with_bio: accounts.filter((a: any) => a.bio).length,
          accounts_with_page_stats: accounts.filter((a: any) =>
            a.follower_count_text || a.following_count_text || a.post_count_text
          ).length,
          verified_percentage: 0,
          bio_percentage: 0,
        };

        if (accounts.length > 0) {
          summary.verified_percentage = (summary.verified_accounts / summary.total_accounts) * 100;
          summary.bio_percentage = (summary.accounts_with_bio / summary.total_accounts) * 100;
        }

        const nextResult: AnalysisResult = {
          summary,
          accounts: accounts.map((acc: any) => ({
            username: typeof (acc.username || acc.handle) === 'string' ? (acc.username || acc.handle) : '',
            display_name: typeof (acc.name || acc.display_name) === 'string' ? (acc.name || acc.display_name) : '',
            bio: typeof acc.bio === 'string' ? acc.bio : '',
            is_verified: acc.is_verified || false,
            avatar_url: typeof (acc.profile_picture_url || acc.avatar_url) === 'string' ? (acc.profile_picture_url || acc.avatar_url) : '',
            account_link:
              `https://www.instagram.com/${acc.username || acc.handle}/`,
            follower_count_text: typeof (acc.follower_count_text || acc.followers?.toString()) === 'string' ? (acc.follower_count_text || acc.followers?.toString()) : '',
            following_count_text: typeof (acc.following_count_text || acc.following?.toString()) === 'string' ? (acc.following_count_text || acc.following?.toString()) : '',
            post_count_text: typeof (acc.post_count_text || acc.posts?.toString()) === 'string' ? (acc.post_count_text || acc.posts?.toString()) : '',
            profile_bio: typeof acc.bio === 'string' ? acc.bio : '',
            page_analyzed_at: typeof acc.page_analyzed_at === 'string' ? acc.page_analyzed_at : '',
            page_analysis_error: typeof acc.page_analysis_error === 'string' ? acc.page_analysis_error : undefined,
          })),
          metadata: {
            target_username: content.metadata?.target_username || content.target_username || '',
            workspace_id: workspaceId,
            analyzed_at: content.metadata?.analyzed_at || matchingArtifact.created_at || new Date().toISOString(),
            total_accounts: accounts.length,
            visit_account_pages: content.metadata?.visit_account_pages || false,
          },
        };

        setIsExecuting(false);
        setResult(nextResult);
        if (!completionNotifiedRef.current) {
          completionNotifiedRef.current = true;
          onComplete?.(nextResult);
        }
      }
    } catch {
      // ignore
    }
  }, [baseApiUrl, onComplete, workspaceId]);

  const fetchExecutionDetail = useCallback(async (execId: string): Promise<FollowingExecutionSnapshot | null> => {
    try {
      const response = await fetchWithTimeout(
        `${baseApiUrl}/api/v1/workspaces/${workspaceId}/executions/${execId}`,
        { headers: { 'Content-Type': 'application/json' } }
      );
      if (!response.ok) return null;
      return (await response.json()) as FollowingExecutionSnapshot;
    } catch {
      return null;
    }
  }, [baseApiUrl, workspaceId]);

  const fetchProgressSnapshot = useCallback(async (execId: string): Promise<FollowingProgressSnapshot | null> => {
    try {
      const response = await fetchWithTimeout(
        `${baseApiUrl}/api/v1/workspaces/${workspaceId}/executions/${execId}/progress-snapshot`,
        { headers: { 'Content-Type': 'application/json' } }
      );
      if (!response.ok) return null;
      return (await response.json()) as FollowingProgressSnapshot;
    } catch {
      return null;
    }
  }, [baseApiUrl, workspaceId]);

  const fetchReusableExecution = useCallback(async (opts: {
    username: string;
    userDataDir: string;
    runMode: string;
    visitAccountPages: boolean;
    timeoutMs?: number;
  }): Promise<FollowingExecutionSnapshot | null> => {
    try {
      const response = await fetchWithTimeout(
        `${baseApiUrl}/api/v1/workspaces/${workspaceId}/executions?limit=30&playbook_code=ig_analyze_following&order_by=created_at&order=desc`,
        { headers: { 'Content-Type': 'application/json' } },
        opts.timeoutMs ?? REQUEST_TIMEOUT_MS,
      );
      if (!response.ok) return null;

      const data = await response.json();
      const executions = Array.isArray(data?.executions) ? data.executions : [];
      const normalizedUsername = normalizeUsername(opts.username);
      const normalizedUserDataDir = (opts.userDataDir || '').trim();

      const candidates = executions.filter((item: FollowingExecutionSnapshot) => {
        const status = executionStatus(item);
        if (!['running', 'pending', 'queued', 'paused'].includes(status)) {
          return false;
        }

        const inputs = executionInputs(item);
        const candidateUsername = normalizeUsername(inputs.target_username);
        const candidateUserDataDir = (inputs.user_data_dir || '').toString().trim();
        const candidateRunMode = (inputs.run_mode || 'full').toString().trim();
        const candidateVisit =
          inputs.visit_account_pages == null ? true : Boolean(inputs.visit_account_pages);

        return (
          candidateUsername === normalizedUsername &&
          candidateUserDataDir === normalizedUserDataDir &&
          candidateRunMode === opts.runMode &&
          candidateVisit === opts.visitAccountPages
        );
      });

      if (candidates.length === 0) return null;

      return [...candidates].sort((a, b) => {
        const pa = executionPriority(executionStatus(a));
        const pb = executionPriority(executionStatus(b));
        if (pa !== pb) return pb - pa;
        return executionSortTime(b) - executionSortTime(a);
      })[0] || null;
    } catch {
      return null;
    }
  }, [baseApiUrl, workspaceId]);

  const recoverExecutionAfterStartFailure = useCallback(async (opts: {
    username: string;
    userDataDir: string;
    runMode: string;
    visitAccountPages: boolean;
  }): Promise<FollowingExecutionSnapshot | null> => {
    for (const delayMs of RECOVERY_RETRY_DELAYS_MS) {
      if (delayMs > 0) {
        await wait(delayMs);
      }
      const reusableExecution = await fetchReusableExecution({
        ...opts,
        timeoutMs: RECOVERY_LOOKUP_TIMEOUT_MS,
      });
      if (reusableExecution?.execution_id) {
        return reusableExecution;
      }
    }
    return null;
  }, [fetchReusableExecution]);

  const applyExecutionSnapshot = useCallback((snapshot: FollowingExecutionSnapshot | null, execId?: string | null) => {
    if (!snapshot) return;

    const status = executionStatus(snapshot);
    const effectiveExecId = (execId || snapshot.execution_id || '').toString();

    if (status === 'pending' || status === 'queued' || status === 'paused') {
      setProgress((prev) => ({
        current: prev?.current || 0,
        total: prev?.total || 0,
        status: 'pending',
        currentAccount: prev?.currentAccount,
        stage: prev?.stage,
        updatedAt: prev?.updatedAt,
        pageIndex: prev?.pageIndex,
        pageTotal: prev?.pageTotal,
        secondsPerPage: prev?.secondsPerPage,
        etaSeconds: prev?.etaSeconds,
      }));
      return;
    }

    if (status === 'running') {
      setProgress((prev) => ({
        current: prev?.current || 0,
        total: prev?.total || 0,
        status: prev?.status === 'processing' ? prev.status : 'processing',
        currentAccount: prev?.currentAccount,
        stage: prev?.stage || 'running',
        updatedAt: prev?.updatedAt,
        pageIndex: prev?.pageIndex,
        pageTotal: prev?.pageTotal,
        secondsPerPage: prev?.secondsPerPage,
        etaSeconds: prev?.etaSeconds,
      }));
      return;
    }

    if (status === 'failed' || status === 'error' || status === 'cancelled' || status === 'cancelled_by_user') {
      const message =
        snapshot.failure_reason ||
        snapshot.task?.error ||
        'Execution failed';
      setProgress((prev) => ({
        current: prev?.current || 0,
        total: prev?.total || 0,
        status: 'failed',
        currentAccount: prev?.currentAccount,
        stage: prev?.stage,
        updatedAt: prev?.updatedAt,
        pageIndex: prev?.pageIndex,
        pageTotal: prev?.pageTotal,
        secondsPerPage: prev?.secondsPerPage,
        etaSeconds: prev?.etaSeconds,
      }));
      setError(message);
      setIsExecuting(false);
      return;
    }

    if ((status === 'completed' || status === 'succeeded') && effectiveExecId) {
      setProgress((prev) => ({
        current: prev?.current || 0,
        total: prev?.total || 0,
        status: 'completed',
        currentAccount: prev?.currentAccount,
        stage: prev?.stage,
        updatedAt: prev?.updatedAt,
        pageIndex: prev?.pageIndex,
        pageTotal: prev?.pageTotal,
        secondsPerPage: prev?.secondsPerPage,
        etaSeconds: prev?.etaSeconds,
      }));
      setIsExecuting(false);
      void fetchResultFromArtifacts(effectiveExecId);
    }
  }, [fetchResultFromArtifacts]);

  const fetchProgressFromArtifacts = useCallback(async (execId: string) => {
    try {
      const response = await fetchWithTimeout(
        `${baseApiUrl}/api/v1/workspaces/${workspaceId}/artifacts?playbook_code=ig_analyze_following&limit=200&include_content=false&include_preview=false`,
        { headers: { 'Content-Type': 'application/json' } }
      );

      if (!response.ok) return;

      const data = await response.json();
      const artifacts = data.artifacts || data || [];

      const matchingProgressArtifacts = artifacts.filter((a: any) => {
        const meta = a.metadata || {};
        const metaExec = meta.execution_id || meta.trace_id;
        const artifactExec = a.execution_id;
        return meta.source === 'ig_analyze_following_progress' && (metaExec === execId || artifactExec === execId);
      });

      if (!matchingProgressArtifacts || matchingProgressArtifacts.length === 0) return;

      const progressArtifact = [...matchingProgressArtifacts].sort((a: any, b: any) => {
        const aTime = (parseServerTimestamp(a.updated_at || a.created_at) ?? new Date(a.updated_at || a.created_at || 0)).getTime();
        const bTime = (parseServerTimestamp(b.updated_at || b.created_at) ?? new Date(b.updated_at || b.created_at || 0)).getTime();
        return bTime - aTime;
      })[0];

      if (!progressArtifact) return;

      let content = parseArtifactContent(progressArtifact);
      if (!content && progressArtifact.id) {
        try {
          const single = await fetchWithTimeout(`${baseApiUrl}/api/v1/artifacts/${progressArtifact.id}?include_content=true&include_preview=false`, {
            headers: { 'Content-Type': 'application/json' },
          });
          if (single.ok) {
            const singleData = await single.json();
            content = parseArtifactContent(singleData);
          }
        } catch {
          // ignore
        }
      }
      if (!content) return;

      const accounts = content.accounts || content.discovered_accounts || [];
      if (!Array.isArray(accounts)) return;

      const stage = content?.progress?.stage;
      if (stage === 'error') {
        const errorType = content?.progress?.error_type;
        const errorMessage = content?.progress?.error_message;
        const lastUrl = content?.progress?.last_url;
        const parts = [
          'Execution failed.',
          errorType ? `type=${errorType}` : null,
          errorMessage ? `message=${errorMessage}` : null,
          lastUrl ? `url=${lastUrl}` : null,
        ].filter(Boolean);
        setError(parts.join(' '));
        setIsExecuting(false);
      }

      const summary = content.summary || {
        total_accounts: accounts.length,
        verified_accounts: accounts.filter((a: any) => a.is_verified).length,
        accounts_with_bio: accounts.filter((a: any) => a.bio).length,
        accounts_with_page_stats: accounts.filter((a: any) =>
          a.follower_count_text || a.following_count_text || a.post_count_text
        ).length,
        verified_percentage: 0,
        bio_percentage: 0,
      };

      if (accounts.length > 0) {
        summary.verified_percentage = (summary.verified_accounts / summary.total_accounts) * 100;
        summary.bio_percentage = (summary.accounts_with_bio / summary.total_accounts) * 100;
      }

      const nextResult: AnalysisResult = {
        summary,
        accounts: accounts.map((acc: any) => ({
          username: typeof (acc.username || acc.handle) === 'string' ? (acc.username || acc.handle) : '',
          display_name: typeof (acc.name || acc.display_name) === 'string' ? (acc.name || acc.display_name) : '',
          bio: typeof acc.bio === 'string' ? acc.bio : '',
          is_verified: acc.is_verified || false,
          avatar_url: typeof (acc.profile_picture_url || acc.avatar_url) === 'string' ? (acc.profile_picture_url || acc.avatar_url) : '',
          account_link:
            `https://www.instagram.com/${acc.username || acc.handle}/`,
          follower_count_text: typeof (acc.follower_count_text || acc.followers?.toString()) === 'string' ? (acc.follower_count_text || acc.followers?.toString()) : '',
          following_count_text: typeof (acc.following_count_text || acc.following?.toString()) === 'string' ? (acc.following_count_text || acc.following?.toString()) : '',
          post_count_text: typeof (acc.post_count_text || acc.posts?.toString()) === 'string' ? (acc.post_count_text || acc.posts?.toString()) : '',
          profile_bio: typeof acc.bio === 'string' ? acc.bio : '',
          page_analyzed_at: typeof acc.page_analyzed_at === 'string' ? acc.page_analyzed_at : '',
          page_analysis_error: typeof acc.page_analysis_error === 'string' ? acc.page_analysis_error : undefined,
        })),
        metadata: {
          target_username:
            content.metadata?.target_username || content.target_username || targetUsername,
          workspace_id: workspaceId,
          analyzed_at:
            content.metadata?.analyzed_at ||
            progressArtifact.created_at ||
            new Date().toISOString(),
          total_accounts: accounts.length,
          visit_account_pages: content.metadata?.visit_account_pages || visitAccountPages,
        },
      };

      setResult((prev) => {
        const prevLen = prev?.accounts?.length || 0;
        const shouldAlwaysRefresh =
          stage === 'visiting_pages' || stage === 'completed' || stage === 'error';
        if (!shouldAlwaysRefresh && accounts.length <= prevLen) return prev;
        return nextResult;
      });

      const updatedAt = progressArtifact.updated_at || progressArtifact.created_at || null;
      const pageIndex = typeof content?.progress?.page_index === 'number' ? content.progress.page_index : null;
      const pageTotal = typeof content?.progress?.page_total === 'number' ? content.progress.page_total : null;
      const totalAccounts =
        typeof content?.progress?.total_accounts === 'number' ? content.progress.total_accounts : null;
      const currentAccount =
        typeof content?.progress?.current_account === 'string' ? content.progress.current_account : undefined;

      let secondsPerPage: number | null = visitingPerfRef.current.avgSecondsPerPage;
      if (stage === 'visiting_pages' && updatedAt && pageIndex !== null) {
        const atMs = toTimestampMs(updatedAt);
        const lastAtMs = visitingPerfRef.current.lastAtMs;
        const lastIndex = visitingPerfRef.current.lastIndex;
        if (
          atMs !== null &&
          lastAtMs !== null &&
          lastIndex !== null &&
          pageIndex > lastIndex &&
          atMs > lastAtMs
        ) {
          const deltaSec = (atMs - lastAtMs) / 1000;
          const perPageSec = deltaSec / (pageIndex - lastIndex);
          if (Number.isFinite(perPageSec) && perPageSec > 0) {
            secondsPerPage =
              visitingPerfRef.current.avgSecondsPerPage === null
                ? perPageSec
                : visitingPerfRef.current.avgSecondsPerPage * 0.8 + perPageSec * 0.2;
            visitingPerfRef.current.avgSecondsPerPage = secondsPerPage;
          }
        }
        visitingPerfRef.current.lastAtMs = atMs;
        visitingPerfRef.current.lastIndex = pageIndex;
      }

      const etaSeconds =
        stage === 'visiting_pages' && secondsPerPage !== null && pageIndex !== null && pageTotal !== null
          ? Math.max(0, Math.round(secondsPerPage * Math.max(0, pageTotal - pageIndex)))
          : null;

      const isComplete = stage === 'completed';
      setProgress((prev) => ({
        current: accounts.length,
        total: totalAccounts ?? pageTotal ?? prev?.total ?? 0,
        status: isComplete ? 'completed' : stage === 'error' ? 'failed' : 'processing',
        currentAccount,
        stage,
        updatedAt: updatedAt || undefined,
        pageIndex: pageIndex === null ? undefined : pageIndex,
        pageTotal: pageTotal === null ? undefined : pageTotal,
        secondsPerPage: secondsPerPage === null ? undefined : secondsPerPage,
        etaSeconds: etaSeconds === null ? undefined : etaSeconds,
      }));

      if (stage === 'completed') {
        setIsExecuting(false);
        setResult(nextResult);
        if (!completionNotifiedRef.current) {
          completionNotifiedRef.current = true;
          onComplete?.(nextResult);
        }
      }
    } catch {
      // ignore
    }
  }, [baseApiUrl, workspaceId, targetUsername, visitAccountPages, onComplete]);

  const pollExecutionState = useCallback(async (execId: string) => {
    const progressSnapshot = await fetchProgressSnapshot(execId);
    if (progressSnapshot) {
      const mergedProgress = mergeFollowingProgressSnapshot(progressSnapshot, progress);
      if (mergedProgress) {
        setProgress(mergedProgress);
      }
      const snapshotStatus = (progressSnapshot.task_status || progressSnapshot.execution_context?.status || '').toString().trim().toLowerCase();
      if (snapshotStatus === 'completed' || snapshotStatus === 'succeeded') {
        setIsExecuting(false);
        await fetchResultFromArtifacts(execId);
        return;
      }
      if (snapshotStatus === 'failed' || snapshotStatus === 'error' || snapshotStatus === 'cancelled' || snapshotStatus === 'cancelled_by_user') {
        setProgress((prev) => ({
          current: prev?.current || 0,
          total: prev?.total || 0,
          status: 'failed',
          currentAccount: prev?.currentAccount,
          stage: prev?.stage,
          updatedAt: prev?.updatedAt,
          pageIndex: prev?.pageIndex,
          pageTotal: prev?.pageTotal,
          secondsPerPage: prev?.secondsPerPage,
          etaSeconds: prev?.etaSeconds,
        }));
        setError('Execution failed');
        setIsExecuting(false);
        return;
      }
    }

    const snapshot = await fetchExecutionDetail(execId);
    if (snapshot) {
      applyExecutionSnapshot(snapshot, execId);
      const status = executionStatus(snapshot);
      if (status === 'running' || status === 'completed' || status === 'succeeded' || status === 'failed' || status === 'error') {
        await fetchProgressFromArtifacts(execId);
      }
      return;
    }
    await fetchProgressFromArtifacts(execId);
  }, [applyExecutionSnapshot, fetchExecutionDetail, fetchProgressFromArtifacts, fetchProgressSnapshot, fetchResultFromArtifacts, progress]);

  const handleExecutionEvent = useCallback((event: any) => {
    if (event.type === 'progress') {
      setProgress({
        current: event.current || 0,
        total: event.total || 0,
        status: event.status || 'processing',
        currentAccount: event.current_account,
      });
    } else if (event.type === 'step_complete') {
      if (event.step_id === 'analyze_following') {
        setProgress({
          current: event.total || 0,
          total: event.total || 0,
          status: 'completed',
        });
      }
    } else if (event.type === 'execution_complete') {
      setIsExecuting(false);
      if (event.result) {
        const completedResult = event.result as AnalysisResult;
        setResult(completedResult);
        if (!completionNotifiedRef.current) {
          completionNotifiedRef.current = true;
          onComplete?.(completedResult);
        }
      } else {
        setTimeout(() => {
          if (executionId) {
            fetchResultFromArtifacts(executionId);
          }
        }, 3000);
      }
    } else if (event.type === 'execution_error') {
      setIsExecuting(false);
      setError(event.error || 'Execution failed');
    }
  }, [executionId, fetchResultFromArtifacts, onComplete]);

  const pollArtifactsProgress = useCallback(async () => {
    if (!executionId) return;
    await pollExecutionState(executionId);
  }, [executionId, pollExecutionState]);

  useExecutionPolling({
    executionId: executionId && isExecuting ? executionId : null,
    workspaceId,
    apiUrl: baseApiUrl,
    onUpdate: handleExecutionEvent,
    pollIntervalMs: 3_000,
    // Keep the modal responsive with frequent polling, but avoid another
    // dedicated execution stream competing with the workbench sidebar.
    enableSSE: false,
    enablePollingFallback: true,
    sseDebounceMs: 1_200,
    pollFn: isExecuting ? pollArtifactsProgress : undefined,
  });

  const startAnalysis = useCallback(async () => {
    if (!targetUsername.trim()) {
      setError('Please enter a target username or URL');
      return;
    }

    const username = extractUsername(targetUsername);
    if (!username) {
      setError('Invalid username or URL format');
      return;
    }

    setError(null);
    setResult(null);
    setProgress({
      current: 0,
      total: 0,
      status: 'started',
      stage: 'submitting',
    });
    setIsExecuting(true);
    setExecutionId(null);
    completionNotifiedRef.current = false;

    try {
      const inputs = {
        target_username: username,
        workspace_id: workspaceId,
        visit_account_pages: visitAccountPages,
        max_accounts: maxAccounts || undefined,
        user_data_dir: resolvedUserDataDir,
        run_mode: runMode,
        allow_partial_resume: allowPartialResume,
      };

      const requestBody = { inputs };

      const executionLookup = {
        username,
        userDataDir: resolvedUserDataDir,
        runMode,
        visitAccountPages,
      };

      const reusableExecution = await fetchReusableExecution(executionLookup);
      if (reusableExecution?.execution_id) {
        const reusableId = reusableExecution.execution_id.toString();
        setExecutionId(reusableId);
        applyExecutionSnapshot(reusableExecution, reusableId);
        announceExecutionStarted(reusableId);
        await pollExecutionState(reusableId);
        return;
      }

      const hint = (params.executionBackend || 'auto').trim();
      const url = `${baseApiUrl}/api/v1/playbooks/execute/start?playbook_code=ig_analyze_following&profile_id=default-user&workspace_id=${workspaceId}&auto_execute=true&execution_backend=${encodeURIComponent(hint)}`;

      let response: Response;
      try {
        response = await fetchWithTimeout(url, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(requestBody),
        }, START_REQUEST_TIMEOUT_MS);
      } catch (requestError) {
        setProgress((prev) => ({
          current: prev?.current || 0,
          total: prev?.total || 0,
          status: 'started',
          currentAccount: prev?.currentAccount,
          stage: 'recovering_submission',
          updatedAt: prev?.updatedAt,
          pageIndex: prev?.pageIndex,
          pageTotal: prev?.pageTotal,
          secondsPerPage: prev?.secondsPerPage,
          etaSeconds: prev?.etaSeconds,
        }));
        const recoveredExecution = await recoverExecutionAfterStartFailure(executionLookup);
        if (recoveredExecution?.execution_id) {
          const recoveredId = recoveredExecution.execution_id.toString();
          setExecutionId(recoveredId);
          applyExecutionSnapshot(recoveredExecution, recoveredId);
          announceExecutionStarted(recoveredId);
          await pollExecutionState(recoveredId);
          return;
        }
        throw requestError;
      }

      if (!response.ok) {
        const errorData = await response.json().catch(() => ({}));
        throw new Error(errorData.detail || errorData.error || `Failed to start analysis: ${response.statusText}`);
      }

      const data = await response.json();
      const nextExecutionId = (data?.execution_id || '').toString();
      if (!nextExecutionId) {
        setProgress((prev) => ({
          current: prev?.current || 0,
          total: prev?.total || 0,
          status: 'started',
          currentAccount: prev?.currentAccount,
          stage: 'recovering_submission',
          updatedAt: prev?.updatedAt,
          pageIndex: prev?.pageIndex,
          pageTotal: prev?.pageTotal,
          secondsPerPage: prev?.secondsPerPage,
          etaSeconds: prev?.etaSeconds,
        }));
        const recoveredExecution = await recoverExecutionAfterStartFailure(executionLookup);
        if (recoveredExecution?.execution_id) {
          const recoveredId = recoveredExecution.execution_id.toString();
          setExecutionId(recoveredId);
          applyExecutionSnapshot(recoveredExecution, recoveredId);
          announceExecutionStarted(recoveredId);
          await pollExecutionState(recoveredId);
          return;
        }
        throw new Error('Start request returned without an execution id');
      }
      setExecutionId(nextExecutionId || null);
      if (nextExecutionId) {
        announceExecutionStarted(nextExecutionId);
        await pollExecutionState(nextExecutionId);
      }
    } catch (err) {
      setIsExecuting(false);
      if (isAbortError(err)) {
        setError('The backend is taking too long to acknowledge this analysis. It may still appear in the queue shortly, so check the execution panel before retrying.');
        return;
      }
      setError(err instanceof Error ? err.message : 'Failed to start analysis');
    }
  }, [
    targetUsername,
    workspaceId,
    visitAccountPages,
    maxAccounts,
    resolvedUserDataDir,
    runMode,
    allowPartialResume,
    baseApiUrl,
    fetchReusableExecution,
    recoverExecutionAfterStartFailure,
    applyExecutionSnapshot,
    pollExecutionState,
    announceExecutionStarted,
    params.executionBackend,
  ]);

  return {
    isExecuting,
    executionId,
    progress,
    result,
    error,

    startAnalysis,
  };
}
