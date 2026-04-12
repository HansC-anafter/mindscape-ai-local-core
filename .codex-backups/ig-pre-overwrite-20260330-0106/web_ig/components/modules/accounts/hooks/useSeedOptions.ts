import { useCallback, useEffect, useMemo, useState } from 'react';
import { MindscapeAPIClient } from '@/api/client';

import type { FilterOption } from '../selectors';

const seedOptionsCache = new Map<string, FilterOption[]>();

/**
 * Hook to fetch available IG seeds from the dedicated backend endpoint.
 * This ensures all seeds are available for the dropdown filter regardless of
 * how many artifacts have been loaded via pagination.
 *
 * Counts come directly from the API which parses all artifacts.
 *
 * Auto-refreshes when a new execution starts (via mindscape:execution_started event).
 */
export function useSeedOptions(params: {
    apiUrl: string;
    workspaceId: string;
    allAccounts?: unknown[];
    enabled?: boolean;
    initialDelayMs?: number;
}) {
    const { apiUrl, workspaceId, enabled = true, initialDelayMs = 0 } = params;
    const client = useMemo(() => MindscapeAPIClient.fromBaseUrl(apiUrl), [apiUrl]);
    const cacheKey = `${apiUrl}::${workspaceId}`;
    const [seedOptions, setSeedOptions] = useState<FilterOption[]>(() => seedOptionsCache.get(cacheKey) || []);
    const [loading, setLoading] = useState(false);

    const fetchSeeds = useCallback(async (retryCount = 0) => {
        if (!enabled) return;
        setLoading(true);
        try {
            // Use the unified insights/seeds API as single source of truth
            const response = await client.get(
                `/api/v1/ig/insights/seeds?workspace_id=${encodeURIComponent(workspaceId)}`
            );
            if (!response.ok) {
                console.error('Failed to fetch seeds:', response.statusText);
                // Retry once on server error
                if (retryCount < 1) {
                    setTimeout(() => void fetchSeeds(retryCount + 1), 2000);
                }
                return;
            }
            const data = await response.json();

            // Parse response from insights/seeds API
            const seeds = data.seeds || [];
            const options: FilterOption[] = seeds.map((item: { seed: string; target_count: number }) => ({
                key: `seed:${item.seed}`,
                label: item.seed,
                count: item.target_count,
            }));

            // Fallback for old API response format
            if (options.length === 0 && data.seeds) {
                data.seeds.forEach((seed: string) => {
                    options.push({ key: `seed:${seed}`, label: seed, count: 0 });
                });
            }

            seedOptionsCache.set(cacheKey, options);
            setSeedOptions(options);
        } catch (err) {
            console.error('Failed to fetch seeds:', err);
            // Retry once on network error
            if (retryCount < 1) {
                setTimeout(() => void fetchSeeds(retryCount + 1), 2000);
            }
        } finally {
            setLoading(false);
        }
    }, [cacheKey, client, enabled, workspaceId]);

    // Initial fetch
    useEffect(() => {
        if (!enabled) {
            setLoading(false);
            return;
        }
        if (initialDelayMs > 0 && seedOptionsCache.has(cacheKey)) {
            return;
        }
        if (initialDelayMs > 0) {
            const timer = setTimeout(() => {
                void fetchSeeds();
            }, initialDelayMs);
            return () => clearTimeout(timer);
        }
        void fetchSeeds();
    }, [cacheKey, enabled, fetchSeeds, initialDelayMs]);

    // Listen for execution_started events and refresh seed list after delay
    // This ensures new seeds appear in dropdown without manual refresh
    useEffect(() => {
        if (!enabled) return;
        const handleExecutionStarted = (event: Event) => {
            const detail = (event as CustomEvent).detail;
            // Only handle ig_analyze_following executions in this workspace
            if (detail?.workspaceId === workspaceId && detail?.playbookCode === 'ig_analyze_following') {
                const targetUsername = detail?.targetUsername || detail?.inputs?.target_username;
                if (targetUsername) {
                    // Optimistically add the seed to the dropdown immediately
                    setSeedOptions((prev) => {
                        const exists = prev.some((o) => o.label === targetUsername);
                        if (exists) return prev;
                        return [
                            ...prev,
                            { key: `seed:${targetUsername}`, label: targetUsername, count: 0 },
                        ];
                    });
                }
                // Also refresh from backend after delay to get real counts
                setTimeout(() => {
                    fetchSeeds();
                }, 3000);
            }
        };

        window.addEventListener('mindscape:execution_started', handleExecutionStarted);
        return () => {
            window.removeEventListener('mindscape:execution_started', handleExecutionStarted);
        };
    }, [enabled, fetchSeeds, workspaceId]);

    return {
        seedOptions,
        loading,
        refresh: fetchSeeds,
    };
}
