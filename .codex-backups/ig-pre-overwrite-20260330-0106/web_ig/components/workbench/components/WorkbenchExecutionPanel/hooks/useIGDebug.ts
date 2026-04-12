/**
 * Hook for IG debug data fetching
 */
import { useState, useCallback, useRef, useEffect } from 'react';
import type { IGDebugInfo } from '../types';
import { parseTimestamp } from '../utils/formatters';

interface UseIGDebugOptions {
    apiUrl: string;
    workspaceId: string;
    executionId: string | null;
}

interface UseIGDebugReturn {
    igDebug: IGDebugInfo | null;
    igDebugLoading: boolean;
    igDebugError: string | null;
    igDebugExpanded: boolean;
    setIgDebugExpanded: (expanded: boolean) => void;
    fetchLatestIGDebug: (showLoading?: boolean) => Promise<void>;
    copyExecutionId: () => Promise<void>;
    screenshotUrl: (executionId: string, fullPath: string) => string;
}

type TimedCacheEntry<T> = {
    fetchedAt: number;
    value: T | null;
};

type SeedStatusCacheValue = {
    savedDedupTargets: number | null;
    visitedCount: number | null;
};

const STATUS_CACHE_TTL_MS = 10_000;
const SEED_STATUS_CACHE_TTL_MS = 10_000;

export function useIGDebug(options: UseIGDebugOptions): UseIGDebugReturn {
    const { apiUrl, workspaceId, executionId } = options;

    const [igDebug, setIgDebug] = useState<IGDebugInfo | null>(null);
    const [igDebugLoading, setIgDebugLoading] = useState(false);
    const [igDebugError, setIgDebugError] = useState<string | null>(null);
    const [igDebugExpanded, setIgDebugExpanded] = useState(false);

    const statusDataCacheRef = useRef<Record<string, TimedCacheEntry<Record<string, any>>>>({});
    const seedStatusCacheRef = useRef<Record<string, TimedCacheEntry<SeedStatusCacheValue>>>({});
    const igDebugInFlightRef = useRef(false);

    useEffect(() => {
        setIgDebug(null);
        setIgDebugError(null);
        setIgDebugLoading(false);
        igDebugInFlightRef.current = false;
    }, [executionId, workspaceId]);

    const fetchExecutionStatusData = useCallback(
        async (execId: string, force = false): Promise<Record<string, any> | null> => {
            const key = (execId || '').toString();
            if (!key) return null;
            const now = Date.now();
            const cached = statusDataCacheRef.current[key];
            if (!force && cached && now - cached.fetchedAt < STATUS_CACHE_TTL_MS) {
                return cached.value || null;
            }
            try {
                const resp = await fetch(`${apiUrl}/api/v1/playbooks/execute/${key}/status`, {
                    headers: { 'Content-Type': 'application/json' },
                });
                if (!resp.ok) {
                    statusDataCacheRef.current[key] = { fetchedAt: now, value: null };
                    return null;
                }
                const data = await resp.json().catch(() => ({}));
                statusDataCacheRef.current[key] = { fetchedAt: now, value: data || null };
                return data || null;
            } catch {
                statusDataCacheRef.current[key] = { fetchedAt: now, value: null };
                return null;
            }
        },
        [apiUrl]
    );

    const fetchSeedStatus = useCallback(
        async (seed: string, force = false): Promise<SeedStatusCacheValue> => {
            const normalizedSeed = (seed || '').toString().trim().toLowerCase();
            if (!workspaceId || !normalizedSeed) {
                return { savedDedupTargets: null, visitedCount: null };
            }

            const cacheKey = `${workspaceId}::${normalizedSeed}`;
            const now = Date.now();
            const cached = seedStatusCacheRef.current[cacheKey];
            if (!force && cached && now - cached.fetchedAt < SEED_STATUS_CACHE_TTL_MS) {
                return cached.value || { savedDedupTargets: null, visitedCount: null };
            }

            try {
                const statusResp = await fetch(
                    `${apiUrl}/api/v1/ig/insights/seed-status?workspace_id=${encodeURIComponent(workspaceId)}&seed=${encodeURIComponent(normalizedSeed)}`
                );
                if (!statusResp.ok) {
                    const emptyValue = { savedDedupTargets: null, visitedCount: null };
                    seedStatusCacheRef.current[cacheKey] = { fetchedAt: now, value: emptyValue };
                    return emptyValue;
                }

                const statusData = await statusResp.json().catch(() => ({}));
                const nextValue = {
                    savedDedupTargets: typeof statusData.target_count === 'number' ? statusData.target_count : null,
                    visitedCount: typeof statusData.visited_count === 'number' ? statusData.visited_count : null,
                };
                seedStatusCacheRef.current[cacheKey] = { fetchedAt: now, value: nextValue };
                return nextValue;
            } catch {
                const emptyValue = { savedDedupTargets: null, visitedCount: null };
                seedStatusCacheRef.current[cacheKey] = { fetchedAt: now, value: emptyValue };
                return emptyValue;
            }
        },
        [apiUrl, workspaceId]
    );

    const fetchLatestIGDebug = useCallback(async (showLoading = false) => {
        if (!executionId) return;
        if (igDebugInFlightRef.current) return;
        igDebugInFlightRef.current = true;

        if (showLoading) setIgDebugLoading(true);
        setIgDebugError(null);

        try {
            const snapshotResp = await fetch(
                `${apiUrl}/api/v1/workspaces/${workspaceId}/executions/${executionId}/progress-snapshot`,
                {
                    headers: { 'Content-Type': 'application/json' },
                }
            );
            if (!snapshotResp.ok) {
                if (snapshotResp.status === 404) {
                    setIgDebug(null);
                    return;
                }
                const data = await snapshotResp.json().catch(() => ({}));
                throw new Error((data.detail || snapshotResp.statusText || 'Failed to fetch progress snapshot').toString());
            }
            const snapshot = await snapshotResp.json().catch(() => ({}));

            const progressRaw = snapshot?.progress;
            const progress = (progressRaw && typeof progressRaw === 'object') ? progressRaw : {};
            const artifactMetaRaw = snapshot?.artifact_metadata;
            const artifactMeta = (artifactMetaRaw && typeof artifactMetaRaw === 'object') ? artifactMetaRaw : {};
            const contentMetaRaw = snapshot?.content_metadata;
            const contentMeta = (contentMetaRaw && typeof contentMetaRaw === 'object') ? contentMetaRaw : {};
            const meta = { ...artifactMeta, ...contentMeta };
            const snapshotCtx = (snapshot?.execution_context && typeof snapshot.execution_context === 'object')
                ? snapshot.execution_context
                : {};

            if (!snapshot?.artifact_id && Object.keys(progress).length === 0 && Object.keys(meta).length === 0) {
                setIgDebug(null);
                return;
            }

            const screenshotsRaw = meta?.scroll_debug_screenshots || [];
            const screenshots = Array.isArray(screenshotsRaw) ? screenshotsRaw.filter(Boolean).map((x) => x.toString()) : [];

            const toIntOrNull = (v: any) => {
                const n = typeof v === 'number' ? v : parseInt((v ?? '').toString(), 10);
                return Number.isFinite(n) ? n : null;
            };

            // Fetch persisted targets count
            const seed = (
                meta?.target_username ||
                snapshotCtx?.inputs?.target_username ||
                snapshotCtx?.target_username ||
                ''
            ).toString().trim();
            const currentStage = (progress?.stage || meta?.stage || null) as string | null;
            const { savedDedupTargets, visitedCount } = await fetchSeedStatus(seed, showLoading);

            // Fetch execution status data (heartbeat, runner info, backend hint)
            const snapshotHasExecutionContext =
                Boolean(snapshotCtx?.heartbeat_at) ||
                Boolean(snapshotCtx?.runner_id) ||
                Boolean(snapshotCtx?.execution_backend_hint) ||
                Boolean(snapshotCtx?.inputs?.execution_backend) ||
                Boolean(snapshotCtx?.inputs?.user_data_dir);
            const statusData = snapshotHasExecutionContext
                ? null
                : await fetchExecutionStatusData(executionId, showLoading);
            const execCtx = statusData?.execution_context || {};
            const backendHint = (
                execCtx?.execution_backend_hint ||
                execCtx?.inputs?.execution_backend ||
                snapshotCtx?.execution_backend_hint ||
                snapshotCtx?.inputs?.execution_backend ||
                ''
            ).toString().trim() || null;
            const heartbeatAt = (execCtx?.heartbeat_at || snapshotCtx?.heartbeat_at || null) as string | null;
            const runnerId = (execCtx?.runner_id || snapshotCtx?.runner_id || null) as string | null;
            const sourceProfileRef = (
                meta?.source_profile_ref ||
                snapshotCtx?.inputs?.user_data_dir ||
                execCtx?.inputs?.user_data_dir ||
                null
            ) as string | null;
            const sourceAccountHandle = (meta?.source_account_handle || null) as string | null;

            // Compute health diagnostics
            const now = Date.now();
            let heartbeatAgeSeconds: number | null = null;
            if (heartbeatAt) {
                const hbTs = parseTimestamp(heartbeatAt)?.getTime();
                if (hbTs) heartbeatAgeSeconds = Math.round((now - hbTs) / 1000);
            }

            const updatedAtRaw = (snapshot?.artifact_updated_at || null) as string | null;
            let progressAgeSeconds: number | null = null;
            if (updatedAtRaw) {
                const pTs = parseTimestamp(updatedAtRaw)?.getTime();
                if (pTs) progressAgeSeconds = Math.round((now - pTs) / 1000);
            }

            // During visiting_pages, progress is tracked in DB (visited count)
            // not by updating the artifact. Use heartbeat_at as the effective
            // progress indicator so we don't get false zombie/stale alerts.
            const isVisitingPages = currentStage === 'visiting_pages';

            // effectiveProgressAge: for visiting_pages, use heartbeat age
            // (runner updates task + heartbeat each visit cycle)
            const effectiveProgressAge = isVisitingPages
                ? heartbeatAgeSeconds
                : progressAgeSeconds;

            // effectiveUpdatedAt: for visiting_pages, show heartbeat time
            const effectiveUpdatedAt = isVisitingPages
                ? (heartbeatAt || updatedAtRaw)
                : updatedAtRaw;

            // Zombie: heartbeat is fresh (< 90s) but effective progress stale (> 3 min)
            // During visiting_pages this can only trigger if heartbeat itself is stale
            const isZombie = (
                heartbeatAgeSeconds !== null && heartbeatAgeSeconds < 90 &&
                effectiveProgressAge !== null && effectiveProgressAge > 180
            );

            // Streak ratio: no_new_streak / limit (default 10)
            const noNewStreak = toIntOrNull(progress?.no_new_accounts_streak);
            const STREAK_LIMIT = 10;
            const streakRatio = noNewStreak !== null ? noNewStreak / STREAK_LIMIT : null;

            setIgDebug({
                executionId,
                updatedAt: effectiveUpdatedAt,
                stage: (progress?.stage || meta?.stage || null) as string | null,
                iter: toIntOrNull(progress?.iteration),
                targets: toIntOrNull(progress?.total_accounts ?? meta?.total_accounts),
                expectedFollowing: toIntOrNull(meta?.expected_following_count),
                stopReason: (meta?.scroll_stop_reason || progress?.scroll_stop_reason || null) as string | null,
                listCaptureStatus: (meta?.list_capture_status || null) as string | null,
                executionBackendHint: backendHint,
                visitAccountPages: typeof meta?.visit_account_pages === 'boolean' ? meta.visit_account_pages : null,
                savedDedupTargets,
                visitedCount,
                pageIndex: toIntOrNull(progress?.page_index),
                pageTotal: toIntOrNull(progress?.page_total),
                currentAccount: (progress?.current_account || null) as string | null,
                noChangeCount: toIntOrNull(progress?.no_change_count),
                noNewAccountsStreak: noNewStreak,
                reachedBottom: typeof progress?.reached_bottom === 'boolean' ? progress.reached_bottom : null,
                errorType: (progress?.error_type || null) as string | null,
                errorMessage: (progress?.error_message || null) as string | null,
                scrollMode: (progress?.scroll_mode || null) as string | null,
                runMode: (progress?.run_mode || meta?.run_mode || null) as string | null,
                allowPartialResume: typeof progress?.allow_partial_resume === 'boolean' ? progress.allow_partial_resume : (typeof meta?.allow_partial_resume === 'boolean' ? meta.allow_partial_resume : null),
                sourceProfileRef,
                sourceAccountHandle,
                screenshots,
                // Health diagnostics
                heartbeatAt,
                runnerId,
                heartbeatAgeSeconds,
                progressAgeSeconds,
                isZombie,
                streakRatio,
                riskCooldownUntil: (meta?.risk_cooldown_until || progress?.risk_cooldown_until || null) as string | null,
                riskReason: (meta?.risk_reason || progress?.risk_reason || null) as string | null,
                riskSignalTarget: (meta?.risk_signal_target || progress?.risk_signal_target || null) as string | null,
            });
        } catch (e) {
            setIgDebugError(e instanceof Error ? e.message : 'Unknown error');
        } finally {
            setIgDebugLoading(false);
            igDebugInFlightRef.current = false;
        }
    }, [apiUrl, workspaceId, executionId, fetchExecutionStatusData, fetchSeedStatus]);

    const copyExecutionId = useCallback(async () => {
        const id = (executionId || '').toString();
        if (!id) return;
        try {
            await navigator.clipboard.writeText(id);
        } catch {
            // ignore
        }
    }, [executionId]);

    const screenshotUrl = (execId: string, fullPath: string) => {
        const basename = fullPath.split('/').pop() || fullPath;
        return `${apiUrl}/api/v1/playbooks/execute/${execId}/debug/screenshot?file=${encodeURIComponent(basename)}&_t=${Date.now()}`;
    };

    return {
        igDebug,
        igDebugLoading,
        igDebugError,
        igDebugExpanded,
        setIgDebugExpanded,
        fetchLatestIGDebug,
        copyExecutionId,
        screenshotUrl,
    };
}
